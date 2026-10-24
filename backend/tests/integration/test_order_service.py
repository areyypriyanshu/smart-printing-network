import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.errors import Forbidden, InvalidTransition, PriceChanged, UploadAlreadyUsed
from app.gateways.payments import FakeGateway
from app.models import Order, OrderEvent, Payment, ShopRate, Upload
from app.schemas.order import OrderCreateRequest
from app.services import order_service
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.factories import (
    FAKE_WEBHOOK_SECRET,
    create_full_rate_table,
    create_shop,
    create_upload_row,
    create_user,
)

BASE_PAISE = 200
PAGES = 5
COPIES = 2
EXPECTED_PRICE = PAGES * COPIES * BASE_PAISE


def _request(upload_id: uuid.UUID, shop_id: uuid.UUID, **overrides: object) -> OrderCreateRequest:
    payload: dict[str, object] = {
        "upload_id": upload_id,
        "shop_id": shop_id,
        "paper_size": "A4",
        "color": False,
        "duplex": False,
        "copies": COPIES,
    }
    payload.update(overrides)
    return OrderCreateRequest.model_validate(payload)


def _seed(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor, min_order_paise=0)
    create_full_rate_table(session, shop, base_paise=BASE_PAISE)
    upload = create_upload_row(session, customer=customer, page_count=PAGES)
    return customer.id, shop.id, upload.id


def _create(
    session: Session, customer_id: uuid.UUID, shop_id: uuid.UUID, upload_id: uuid.UUID
) -> Order:
    order, _payment = order_service.create_order(
        session,
        customer_id=customer_id,
        request=_request(upload_id, shop_id),
        idempotency_key="key-1",
        gateway=FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET),
    )
    return order


def test_create_order_snapshots_price_and_options(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)

    order = _create(db_session, customer_id, shop_id, upload_id)

    assert order.status == "PENDING_PAYMENT"
    assert order.page_count == PAGES
    assert order.rate_paise == BASE_PAISE
    assert order.min_order_paise == 0
    assert order.price_paise == EXPECTED_PRICE
    assert order.copies == COPIES
    assert order.pickup_code is None
    assert order.paid_at is None
    assert order.order_no > 0


def test_create_order_writes_one_creation_event(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)

    order = _create(db_session, customer_id, shop_id, upload_id)

    events = list(db_session.scalars(select(OrderEvent).where(OrderEvent.order_id == order.id)))
    assert len(events) == 1
    assert events[0].from_status is None
    assert events[0].to_status == "PENDING_PAYMENT"
    assert events[0].actor_type == "customer"


def test_injected_clock_is_shared_by_order_fields_and_events(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    order, _payment = order_service.create_order(
        db_session,
        customer_id=customer_id,
        request=_request(upload_id, shop_id),
        idempotency_key="clock-key",
        gateway=FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET),
        now=created_at,
    )
    times = [created_at + timedelta(minutes=offset) for offset in (5, 6, 7, 17)]
    for status, at in zip(("PAID", "ACCEPTED", "PRINTING", "READY"), times, strict=True):
        order_service.transition(
            db_session,
            order_id=order.id,
            to_status=status,
            actor_type="webhook" if status == "PAID" else "vendor",
            now=at,
        )

    events = list(
        db_session.scalars(
            select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.id)
        )
    )
    assert [event.at for event in events] == [created_at, *times]
    assert order.created_at == created_at
    assert order.reserved_at == times[0]
    assert order.ready_at == times[-1]
    assert events[0].at == order.created_at
    assert events[1].at == order.reserved_at
    assert events[-1].at == order.ready_at


def test_create_order_keeps_the_file_alive(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)

    _create(db_session, customer_id, shop_id, upload_id)

    upload = db_session.get(Upload, upload_id)
    assert upload is not None
    assert upload.delete_after is None


def test_duplicate_idempotency_key_returns_the_same_order(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)

    first = _create(db_session, customer_id, shop_id, upload_id)
    second, _payment = order_service.create_order(
        db_session,
        customer_id=customer_id,
        request=_request(upload_id, shop_id),
        idempotency_key="key-1",
        gateway=FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET),
    )

    assert second.id == first.id
    orders = list(db_session.scalars(select(Order).where(Order.customer_id == customer_id)))
    assert len(orders) == 1


def test_expected_price_mismatch_raises_price_changed(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)

    with pytest.raises(PriceChanged) as error:
        order_service.create_order(
            db_session,
            customer_id=customer_id,
            request=_request(upload_id, shop_id, expected_price_paise=EXPECTED_PRICE + 1),
            idempotency_key="key-1",
            gateway=FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET),
        )

    assert error.value.details["current_price_paise"] == EXPECTED_PRICE
    assert db_session.scalar(select(Order).where(Order.customer_id == customer_id)) is None


def test_rate_change_after_creation_does_not_change_the_order(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)

    rate = db_session.scalar(
        select(ShopRate).where(
            ShopRate.shop_id == shop_id,
            ShopRate.paper_size == "A4",
            ShopRate.color.is_(False),
            ShopRate.duplex.is_(False),
        )
    )
    assert rate is not None
    rate.rate_paise = BASE_PAISE * 2
    db_session.commit()

    db_session.refresh(order)
    assert order.rate_paise == BASE_PAISE
    assert order.price_paise == EXPECTED_PRICE


def test_second_order_for_the_same_upload_is_rejected(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    _create(db_session, customer_id, shop_id, upload_id)

    with pytest.raises(UploadAlreadyUsed):
        order_service.create_order(
            db_session,
            customer_id=customer_id,
            request=_request(upload_id, shop_id),
            idempotency_key="key-2",
            gateway=FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET),
        )


def test_transition_to_paid_sets_paid_at_and_pickup_code(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)

    paid = order_service.transition(
        db_session,
        order_id=order.id,
        to_status="PAID",
        actor_type="webhook",
    )

    assert paid.status == "PAID"
    assert paid.paid_at is not None
    assert paid.pickup_code is not None
    assert len(paid.pickup_code) == 6
    assert paid.pickup_code.isdigit()

    events = list(
        db_session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == order.id)
            .order_by(OrderEvent.at.asc(), OrderEvent.id.asc())
        )
    )
    assert [event.to_status for event in events] == ["PENDING_PAYMENT", "PAID"]
    assert events[1].from_status == "PENDING_PAYMENT"
    assert events[1].actor_type == "webhook"


def test_transition_to_a_terminal_status_schedules_file_deletion(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)

    order_service.transition(
        db_session, order_id=order.id, to_status="EXPIRED", actor_type="system"
    )

    upload = db_session.get(Upload, upload_id)
    assert upload is not None
    assert upload.delete_after is not None


def test_illegal_transition_raises_invalid_transition(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)

    with pytest.raises(InvalidTransition):
        order_service.transition(
            db_session, order_id=order.id, to_status="READY", actor_type="vendor"
        )


def test_wrong_actor_for_a_transition_is_forbidden(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)

    with pytest.raises(Forbidden):
        order_service.transition(
            db_session, order_id=order.id, to_status="PAID", actor_type="customer"
        )


def test_a_failing_event_insert_rolls_back_the_status_change(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)

    class BrokenEvent(OrderEvent):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**{**kwargs, "to_status": None})

    monkeypatch.setattr(order_service, "OrderEvent", BrokenEvent)

    with pytest.raises(IntegrityError):
        order_service.transition(
            db_session, order_id=order.id, to_status="PAID", actor_type="webhook"
        )
    db_session.rollback()

    stored = db_session.get(Order, order.id)
    assert stored is not None
    assert stored.status == "PENDING_PAYMENT"
    assert stored.paid_at is None
    assert stored.pickup_code is None
    events = list(db_session.scalars(select(OrderEvent).where(OrderEvent.order_id == order.id)))
    assert [event.to_status for event in events] == ["PENDING_PAYMENT"]


def _capture_payment(db_session: Session, order: Order) -> Payment:
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    payment.status = "CAPTURED"
    payment.provider_payment_id = f"pay_test_{payment.id}"
    db_session.commit()
    return payment


def test_rejecting_a_paid_order_queues_a_refund(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)
    order_service.transition(db_session, order_id=order.id, to_status="PAID", actor_type="webhook")
    _capture_payment(db_session, order)

    order_service.transition(
        db_session, order_id=order.id, to_status="REJECTED", actor_type="vendor", reason="no"
    )

    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "REFUND_PENDING"
    assert payment.refund_next_attempt_at is not None


def test_cancelling_a_paid_order_queues_a_refund(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)
    order_service.transition(db_session, order_id=order.id, to_status="PAID", actor_type="webhook")
    _capture_payment(db_session, order)

    order_service.transition(
        db_session, order_id=order.id, to_status="CANCELLED", actor_type="customer"
    )

    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "REFUND_PENDING"


def test_cancelling_an_unpaid_order_queues_no_refund(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)

    order_service.transition(
        db_session, order_id=order.id, to_status="CANCELLED", actor_type="customer"
    )

    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"
    assert payment.refund_next_attempt_at is None


def test_the_pickup_code_never_changes_after_payment(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)

    order_service.transition(db_session, order_id=order.id, to_status="PAID", actor_type="webhook")
    paid = db_session.get(Order, order.id)
    assert paid is not None
    original = paid.pickup_code

    order_service.transition(
        db_session, order_id=order.id, to_status="ACCEPTED", actor_type="vendor"
    )
    order_service.transition(
        db_session, order_id=order.id, to_status="PRINTING", actor_type="vendor"
    )
    order_service.transition(db_session, order_id=order.id, to_status="READY", actor_type="vendor")

    stored = db_session.get(Order, order.id)
    assert stored is not None
    assert stored.pickup_code == original


def test_the_refund_flag_and_the_status_change_commit_together(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    order = _create(db_session, customer_id, shop_id, upload_id)
    order_service.transition(db_session, order_id=order.id, to_status="PAID", actor_type="webhook")
    _capture_payment(db_session, order)

    def broken_refund(*args: object, **kwargs: object) -> None:
        raise RuntimeError("refund queueing failed")

    monkeypatch.setattr(order_service, "_queue_refund", broken_refund)

    with pytest.raises(RuntimeError):
        order_service.transition(
            db_session, order_id=order.id, to_status="REJECTED", actor_type="vendor"
        )
    db_session.rollback()

    stored = db_session.get(Order, order.id)
    assert stored is not None
    assert stored.status == "PAID"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CAPTURED"
