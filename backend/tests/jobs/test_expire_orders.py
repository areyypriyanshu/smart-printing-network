"""Tests for the expire_orders job.

The clock is injected, so these tests do not sleep and do not depend on
when they run.
"""

from datetime import UTC, datetime, timedelta

from app.jobs import expire_orders
from app.models import Order, OrderEvent, Upload
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_shop,
    create_unpaid_order,
    create_user,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
PAST = NOW - timedelta(minutes=20)


def _unpaid_order(session: Session) -> Order:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    return create_unpaid_order(session, customer=customer, shop=shop, created_at=PAST)


def test_an_unpaid_order_past_the_window_expires(db_session: Session) -> None:
    order = _unpaid_order(db_session)

    expired = expire_orders.run(db_session, now=NOW)

    assert expired == 1
    db_session.refresh(order)
    assert order.status == "EXPIRED"
    assert order.status_reason == "payment_timeout"


def test_an_order_inside_the_window_is_left_alone(db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    order = create_unpaid_order(db_session, customer=customer, shop=shop)
    order.created_at = NOW - timedelta(minutes=5)
    db_session.commit()

    expired = expire_orders.run(db_session, now=NOW)

    assert expired == 0
    db_session.refresh(order)
    assert order.status == "PENDING_PAYMENT"


def test_running_the_job_twice_expiries_nothing_the_second_time(
    db_session: Session,
) -> None:
    _unpaid_order(db_session)

    first = expire_orders.run(db_session, now=NOW)
    second = expire_orders.run(db_session, now=NOW)

    assert first == 1
    assert second == 0


def test_expiry_writes_an_event(db_session: Session) -> None:
    order = _unpaid_order(db_session)

    expire_orders.run(db_session, now=NOW)

    events = list(
        db_session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == order.id)
            .order_by(OrderEvent.at.asc(), OrderEvent.id.asc())
        )
    )
    assert [event.to_status for event in events] == ["PENDING_PAYMENT", "EXPIRED"]
    assert events[1].actor_type == "system"
    assert events[1].reason == "payment_timeout"


def test_expiry_schedules_the_file_for_deletion(db_session: Session) -> None:
    order = _unpaid_order(db_session)

    expire_orders.run(db_session, now=NOW)

    upload = db_session.get(Upload, order.upload_id)
    assert upload is not None
    assert upload.delete_after is not None
    assert upload.delete_after > NOW
