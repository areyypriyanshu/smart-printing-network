"""Tests for the auto_reject job.

An order reaches the queue once it is reserved and paid in cash at the
counter. If no shop takes it, the order is rejected. No money was taken,
so nothing is refunded.
"""

from datetime import UTC, datetime, timedelta

from app.jobs import auto_reject
from app.models import Order, OrderEvent, Payment, Shop, User
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_paid_order,
    create_reserved_order,
    create_shop,
    create_user,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
PAST = NOW - timedelta(minutes=20)


def _customer_and_shop(session: Session) -> tuple[User, Shop]:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    return customer, shop


def _reserved_order(session: Session, *, minutes_ago: int = 20) -> Order:
    customer, shop = _customer_and_shop(session)
    return create_reserved_order(
        session,
        customer=customer,
        shop=shop,
        reserved_at=NOW - timedelta(minutes=minutes_ago),
    )


def test_a_reserved_order_past_the_accept_window_is_rejected(db_session: Session) -> None:
    order = _reserved_order(db_session)

    rejected = auto_reject.run(db_session, now=NOW)

    assert rejected == 1
    db_session.refresh(order)
    assert order.status == "REJECTED"
    assert order.status_reason == "shop_timeout"


def test_a_reserved_order_inside_the_window_is_left_alone(db_session: Session) -> None:
    order = _reserved_order(db_session, minutes_ago=5)

    rejected = auto_reject.run(db_session, now=NOW)

    assert rejected == 0
    db_session.refresh(order)
    assert order.status == "RESERVED"


def test_rejection_takes_no_money(db_session: Session) -> None:
    order = _reserved_order(db_session)

    auto_reject.run(db_session, now=NOW)

    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"
    assert payment.refund_next_attempt_at is None


def test_rejection_writes_an_event(db_session: Session) -> None:
    order = _reserved_order(db_session)

    auto_reject.run(db_session, now=NOW)

    events = list(
        db_session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == order.id)
            .order_by(OrderEvent.at.asc(), OrderEvent.id.asc())
        )
    )
    assert [event.to_status for event in events] == ["RESERVED", "REJECTED"]
    assert events[1].actor_type == "system"


def test_running_the_job_twice_rejects_nothing_the_second_time(
    db_session: Session,
) -> None:
    _reserved_order(db_session)

    first = auto_reject.run(db_session, now=NOW)
    second = auto_reject.run(db_session, now=NOW)

    assert first == 1
    assert second == 0


def test_an_accepted_order_is_never_auto_rejected(db_session: Session) -> None:
    from app.services import order_service

    order = _reserved_order(db_session)
    order_service.transition(
        db_session, order_id=order.id, to_status="ACCEPTED", actor_type="vendor"
    )

    rejected = auto_reject.run(db_session, now=NOW)

    assert rejected == 0
    db_session.refresh(order)
    assert order.status == "ACCEPTED"


def test_a_historical_paid_order_past_the_window_is_still_rejected(
    db_session: Session,
) -> None:
    """A row left in PAID by the online version is still the shop's work."""
    customer, shop = _customer_and_shop(db_session)
    paid_at = NOW - timedelta(minutes=20)
    order = create_paid_order(
        db_session,
        customer=customer,
        shop=shop,
        created_at=paid_at - timedelta(minutes=1),
        paid_at=paid_at,
    )

    rejected = auto_reject.run(db_session, now=NOW)

    assert rejected == 1
    db_session.refresh(order)
    assert order.status == "REJECTED"
    assert order.status_reason == "shop_timeout"
