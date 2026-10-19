"""Tests for the process_refunds job.

The money has to go back, and it must not go back twice. Both matter.
"""

from datetime import UTC, datetime, timedelta

from app.gateways.payments import GatewayError
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


def _payment_pending_refund(session: Session) -> Payment:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    order = create_paid_order(session, customer=customer, shop=shop)
    payment = session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    payment.status = "REFUND_PENDING"
    payment.refund_next_attempt_at = NOW - timedelta(minutes=1)
    session.commit()
    return payment


def test_a_pending_refund_is_sent(db_session: Session) -> None:
    payment = _payment_pending_refund(db_session)
    gateway = RecordingGateway()

    refunded = process_refunds.run(db_session, now=NOW, gateway=gateway)

    assert refunded == 1
    db_session.refresh(payment)
    assert payment.status == "REFUNDED"
    assert payment.refund_id is not None
    assert payment.refund_next_attempt_at is None
    assert gateway.refund_calls[0]["provider_payment_id"] == payment.provider_payment_id
    assert gateway.refund_calls[0]["amount_paise"] == payment.amount_paise


def test_the_refund_reference_is_the_same_on_every_attempt(db_session: Session) -> None:
    payment = _payment_pending_refund(db_session)
    gateway = RecordingGateway()

    process_refunds.run(db_session, now=NOW, gateway=gateway)

    assert gateway.refund_calls[0]["idempotency_note"] == f"refund:{payment.id}"


def test_running_the_job_twice_refunds_nothing_the_second_time(
    db_session: Session,
) -> None:
    _payment_pending_refund(db_session)
    gateway = RecordingGateway()

    first = process_refunds.run(db_session, now=NOW, gateway=gateway)
    second = process_refunds.run(db_session, now=NOW, gateway=gateway)

    assert first == 1
    assert second == 0
    assert len(gateway.refund_calls) == 1


def test_a_refund_is_not_sent_before_its_next_attempt_time(db_session: Session) -> None:
    payment = _payment_pending_refund(db_session)
    payment.refund_next_attempt_at = NOW + timedelta(minutes=5)
    db_session.commit()
    gateway = RecordingGateway()

    refunded = process_refunds.run(db_session, now=NOW, gateway=gateway)

    assert refunded == 0
    assert gateway.refund_calls == []


def test_a_failed_refund_is_retried_later(db_session: Session) -> None:
    payment = _payment_pending_refund(db_session)
    gateway = RecordingGateway(refund_error=GatewayError("gateway is down"))

    refunded = process_refunds.run(db_session, now=NOW, gateway=gateway)

    assert refunded == 0
    db_session.refresh(payment)
    assert payment.status == "REFUND_PENDING"
    assert payment.refund_attempts == 1
    assert payment.refund_next_attempt_at == NOW + timedelta(minutes=1)


def test_a_refund_that_failed_twice_waits_longer(db_session: Session) -> None:
    payment = _payment_pending_refund(db_session)
    gateway = RecordingGateway(refund_error=GatewayError("gateway is down"))

    process_refunds.run(db_session, now=NOW, gateway=gateway)
    process_refunds.run(db_session, now=NOW + timedelta(minutes=1), gateway=gateway)

    db_session.refresh(payment)
    assert payment.refund_attempts == 2
    assert payment.refund_next_attempt_at == NOW + timedelta(minutes=1) + timedelta(minutes=2)


def test_a_payment_without_a_captured_id_is_marked_failed(
    db_session: Session,
) -> None:
    payment = _payment_pending_refund(db_session)
    payment.provider_payment_id = None
    db_session.commit()
    gateway = RecordingGateway()

    refunded = process_refunds.run(db_session, now=NOW, gateway=gateway)

    assert refunded == 0
    db_session.refresh(payment)
    assert payment.status == "FAILED"
    assert gateway.refund_calls == []
