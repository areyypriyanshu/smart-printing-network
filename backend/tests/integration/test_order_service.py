import uuid

import pytest
from app.errors import Forbidden, InvalidTransition, PriceChanged, UploadAlreadyUsed
from app.models import Order, OrderEvent, ShopRate, Upload
from app.schemas.order import OrderCreateRequest
from app.services import order_service
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.factories import (
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


def _create(session: Session, customer_id: uuid.UUID, shop_id: uuid.UUID, upload_id: uuid.UUID):
    return order_service.create_order(
        session,
        customer_id=customer_id,
        request=_request(upload_id, shop_id),
        idempotency_key="key-1",
    )


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


def test_create_order_keeps_the_file_alive(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)

    _create(db_session, customer_id, shop_id, upload_id)

    upload = db_session.get(Upload, upload_id)
    assert upload is not None
    assert upload.delete_after is None


def test_duplicate_idempotency_key_returns_the_same_order(db_session: Session) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)

    first = _create(db_session, customer_id, shop_id, upload_id)
    second = order_service.create_order(
        db_session,
        customer_id=customer_id,
        request=_request(upload_id, shop_id),
        idempotency_key="key-1",
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
