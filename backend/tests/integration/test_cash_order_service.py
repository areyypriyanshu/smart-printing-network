"""The order lifecycle at the service level.

The API tests show the behaviour from outside. These show the things
that only the service can prove: that the cash capture and the status
change commit together, and that a reservation never touches money.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.errors import InvalidTransition
from app.models import Order, OrderEvent, Payment, Upload
from app.schemas.order import OrderCreateRequest
from app.services import order_service
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_paid_order,
    create_reserved_order,
    create_shop,
    create_upload_row,
    create_user,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _seed(session: Session) -> tuple[object, object]:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    return customer, shop


def _request(upload_id: uuid.UUID, shop_id: uuid.UUID) -> OrderCreateRequest:
    return OrderCreateRequest(
        upload_id=upload_id,
        shop_id=shop_id,
        paper_size="A4",
        color=False,
        duplex=False,
        copies=1,
    )


def test_creating_an_order_reserves_it_and_records_a_cash_payment(
    db_session: Session,
) -> None:
    customer, shop = _seed(db_session)
    upload = create_upload_row(db_session, customer=customer, page_count=1)

    order = order_service.create_order(
        db_session,
        customer_id=customer.id,
        request=_request(upload.id, shop.id),
        idempotency_key=uuid.uuid4().hex,
    )

    assert order.status == "RESERVED"
    assert order.payment_method == "at_store"
    assert order.paid_at is None
    assert order.reserved_at is not None
    assert order.pickup_code is not None
    assert len(order.pickup_code) == 6
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.provider == "cash"
    assert payment.status == "CREATED"
    assert payment.amount_paise == order.price_paise
    assert payment.currency == "INR"


def test_an_order_records_one_opening_event(db_session: Session) -> None:
    """It is booked in one step. It never passes through PENDING_PAYMENT."""
    customer, shop = _seed(db_session)
    upload = create_upload_row(db_session, customer=customer, page_count=1)

    order = order_service.create_order(
        db_session,
        customer_id=customer.id,
        request=_request(upload.id, shop.id),
        idempotency_key=uuid.uuid4().hex,
    )

    events = list(
        db_session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == order.id)
            .order_by(OrderEvent.at.asc(), OrderEvent.id.asc())
        )
    )
    assert len(events) == 1
    assert events[0].from_status is None
    assert events[0].to_status == "RESERVED"
    assert events[0].actor_type == "customer"


def test_collecting_an_order_captures_the_money(db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    for to_status in ("ACCEPTED", "PRINTING", "READY"):
        order_service.transition(
            db_session, order_id=order.id, to_status=to_status, actor_type="vendor"
        )

    collected = order_service.transition(
        db_session, order_id=order.id, to_status="COLLECTED", actor_type="vendor"
    )

    assert collected.status == "COLLECTED"
    assert collected.paid_at is not None
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CAPTURED"
    assert payment.provider_payment_id is not None


def test_an_order_cannot_be_collected_twice(db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    for to_status in ("ACCEPTED", "PRINTING", "READY"):
        order_service.transition(
            db_session, order_id=order.id, to_status=to_status, actor_type="vendor"
        )
    order_service.transition(
        db_session, order_id=order.id, to_status="COLLECTED", actor_type="vendor"
    )

    with pytest.raises(InvalidTransition):
        order_service.transition(
            db_session, order_id=order.id, to_status="COLLECTED", actor_type="vendor"
        )

    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CAPTURED"
    events = db_session.scalars(
        select(OrderEvent).where(
            OrderEvent.order_id == order.id, OrderEvent.to_status == "COLLECTED"
        )
    ).all()
    assert len(events) == 1


def test_the_capture_and_the_status_change_commit_together(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A collected order without a recorded payment would be a money leak."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    for to_status in ("ACCEPTED", "PRINTING", "READY"):
        order_service.transition(
            db_session, order_id=order.id, to_status=to_status, actor_type="vendor"
        )

    def broken_capture(*args: object, **kwargs: object) -> None:
        raise RuntimeError("capture failed")

    monkeypatch.setattr(order_service, "_capture_cash_payment", broken_capture)

    with pytest.raises(RuntimeError):
        order_service.transition(
            db_session, order_id=order.id, to_status="COLLECTED", actor_type="vendor"
        )
    db_session.rollback()

    stored = db_session.get(Order, order.id)
    assert stored is not None
    assert stored.status == "READY"
    assert stored.paid_at is None
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"


def test_collecting_an_order_creates_no_refund_row(db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    for to_status in ("ACCEPTED", "PRINTING", "READY"):
        order_service.transition(
            db_session, order_id=order.id, to_status=to_status, actor_type="vendor"
        )

    order_service.transition(
        db_session, order_id=order.id, to_status="COLLECTED", actor_type="vendor"
    )

    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CAPTURED"
    assert payment.refund_id is None
    assert payment.refund_attempts == 0
    assert payment.refund_next_attempt_at is None


def test_rejecting_an_order_takes_no_money(db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)

    rejected = order_service.transition(
        db_session, order_id=order.id, to_status="REJECTED", actor_type="vendor"
    )

    assert rejected.status == "REJECTED"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"
    assert payment.refund_next_attempt_at is None


def test_cancelling_an_order_takes_no_money(db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)

    cancelled = order_service.transition(
        db_session, order_id=order.id, to_status="CANCELLED", actor_type="customer"
    )

    assert cancelled.status == "CANCELLED"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"
    assert payment.refund_next_attempt_at is None


def test_a_historical_paid_order_can_be_rejected_without_a_refund(db_session: Session) -> None:
    """No online provider is left to refund through; this is the documented gap.

    The money of a row booked online before cash-only was taken by the
    provider. Rejecting it leaves the payment record untouched for a
    person to settle; the application does not pretend it refunded.
    """
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)

    rejected = order_service.transition(
        db_session, order_id=order.id, to_status="REJECTED", actor_type="vendor"
    )

    assert rejected.status == "REJECTED"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CAPTURED"
    assert payment.refund_next_attempt_at is None


def test_an_order_never_becomes_paid_through_a_transition(db_session: Session) -> None:
    """There is no legal way to reach PAID from RESERVED."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)

    with pytest.raises(InvalidTransition):
        order_service.transition(
            db_session, order_id=order.id, to_status="PAID", actor_type="vendor"
        )


def test_the_pickup_code_never_changes(db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    original = order.pickup_code

    for to_status in ("ACCEPTED", "PRINTING", "READY", "COLLECTED"):
        stored = order_service.transition(
            db_session, order_id=order.id, to_status=to_status, actor_type="vendor"
        )
        assert stored.pickup_code == original


def test_an_order_releases_its_file_when_it_reaches_a_terminal_state(
    db_session: Session,
) -> None:
    """The PDF is deleted by the purge job once the order is done."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)

    order_service.transition(
        db_session, order_id=order.id, to_status="REJECTED", actor_type="vendor"
    )

    upload = db_session.get(Upload, order.upload_id)
    assert upload is not None
    assert upload.delete_after is not None


def test_an_order_cannot_be_collected_before_the_shop_accepts_it(
    db_session: Session,
) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)

    with pytest.raises(InvalidTransition):
        order_service.transition(
            db_session, order_id=order.id, to_status="COLLECTED", actor_type="vendor"
        )


def test_an_order_keeps_its_place_in_the_queue(db_session: Session) -> None:
    """The queue is ordered by when the order was reserved."""
    customer, shop = _seed(db_session)
    earlier = create_reserved_order(
        db_session,
        customer=customer,
        shop=shop,
        reserved_at=NOW - timedelta(minutes=30),
    )
    later = create_reserved_order(
        db_session,
        customer=customer,
        shop=shop,
        reserved_at=NOW - timedelta(minutes=5),
    )

    from app.services import vendor_service

    queue = vendor_service.list_queue(db_session, shop_id=shop.id, limit=10)

    assert [item.id for item in queue.items] == [earlier.id, later.id]
    assert all(item.paid_at is None for item in queue.items)
