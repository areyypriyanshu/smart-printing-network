"""A refund that is owed must actually be sent.

The refund job selects the payments that are waiting for a refund. The
next-attempt time is the schedule, not the permission: a writer that
forgot to set it must not leave the money in the platform's pocket for
ever. A payment that is waiting for a refund with no time set is still
waiting for a refund, and it is picked up.
"""

from datetime import UTC, datetime, timedelta

from app.jobs import process_refunds
from app.models import Payment
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    RecordingGateway,
    create_full_rate_table,
    create_paid_order,
    create_shop,
    create_user,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _payment_waiting_for_a_refund(session: Session) -> Payment:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    order = create_paid_order(session, customer=customer, shop=shop)
    payment = session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    payment.status = "REFUND_PENDING"
    session.commit()
    return payment


def test_a_refund_with_no_schedule_is_still_sent(db_session: Session) -> None:
    """The time is the schedule, not the permission.

    A payment that is waiting for a refund and has no next-attempt time
    is a refund that is owed. It is picked up, so a writer that forgot
    the time cannot keep the money for ever.
    """
    payment = _payment_waiting_for_a_refund(db_session)
    assert payment.refund_next_attempt_at is None
    gateway = RecordingGateway()

    refunded = process_refunds.run(db_session, now=NOW, gateway=gateway)

    assert refunded == 1
    db_session.refresh(payment)
    assert payment.status == "REFUNDED"
    assert payment.refund_id is not None


def test_a_refund_that_is_not_due_yet_is_left_alone(db_session: Session) -> None:
    """The schedule still holds a payment back until it is due."""
    payment = _payment_waiting_for_a_refund(db_session)
    payment.refund_next_attempt_at = NOW + timedelta(minutes=5)
    db_session.commit()
    gateway = RecordingGateway()

    refunded = process_refunds.run(db_session, now=NOW, gateway=gateway)

    assert refunded == 0
    db_session.refresh(payment)
    assert payment.status == "REFUND_PENDING"


def test_the_job_is_safe_to_run_twice(db_session: Session) -> None:
    """A payment that has been refunded is no longer waiting for one."""
    _payment_waiting_for_a_refund(db_session)
    gateway = RecordingGateway()

    first = process_refunds.run(db_session, now=NOW, gateway=gateway)
    second = process_refunds.run(db_session, now=NOW, gateway=gateway)

    assert first == 1
    assert second == 0
    assert len(gateway.refund_calls) == 1
