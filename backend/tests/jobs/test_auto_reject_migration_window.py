"""The window while a column is being added.

`reserved_at` is the moment an order entered the shop's queue. It was
added by a migration, so the rows the previous version of the application
wrote have no value in it. Those rows still have to be rejected when no
shop takes them, and their money still has to go back.
"""

from datetime import UTC, datetime, timedelta

from app.jobs import auto_reject
from app.models import Order
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_paid_order,
    create_shop,
    create_user,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _order_without_a_reserved_at(session: Session, *, minutes_ago: int) -> Order:
    """An order written by the version before the column existed.

    It was paid at a known time, and it has no value in the new column,
    because the version that wrote it did not know the column.
    """
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    order = create_paid_order(session, customer=customer, shop=shop)
    order.paid_at = NOW - timedelta(minutes=minutes_ago)
    order.reserved_at = None
    session.commit()
    return order


def test_an_order_without_a_reserved_at_is_still_rejected(db_session: Session) -> None:
    """The fallback is the moment the order was paid.

    The order was in the queue since it was paid, so the wait is
    measured from then, exactly as the version before the column
    measured it.
    """
    order = _order_without_a_reserved_at(db_session, minutes_ago=20)

    rejected = auto_reject.run(db_session, now=NOW)

    assert rejected == 1
    db_session.refresh(order)
    assert order.status == "REJECTED"
    assert order.status_reason == "shop_timeout"


def test_an_order_without_a_reserved_at_inside_the_window_is_left_alone(
    db_session: Session,
) -> None:
    order = _order_without_a_reserved_at(db_session, minutes_ago=5)

    rejected = auto_reject.run(db_session, now=NOW)

    assert rejected == 0
    db_session.refresh(order)
    assert order.status == "PAID"


def test_an_order_with_a_reserved_at_still_uses_it(db_session: Session) -> None:
    """The new column is the one that is read, when it has a value."""
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    order.paid_at = NOW - timedelta(minutes=1)
    order.reserved_at = NOW - timedelta(minutes=20)
    db_session.commit()

    rejected = auto_reject.run(db_session, now=NOW)

    assert rejected == 1
    db_session.refresh(order)
    assert order.status == "REJECTED"
