"""The payment landing while the order goes away.

The capture at the provider and the state change on the order are two
things that happen at two different times. The order can go terminal in
between, and the money still has to go back.

These tests use real connections and real commits, because a race cannot
be shown inside a transaction that nobody else can see. They commit
their own data, so they do not use the shared `db_session` fixture, and
they clean up after themselves.
"""

import json
import uuid

import pytest
from app.errors import InvalidTransition
from app.gateways.payments import FakeGateway
from app.models import Order, OrderEvent, Payment, Shop, ShopRate, Upload, User, WebhookEvent
from app.schemas.order import OrderCreateRequest
from app.services import order_service, payment_service
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from tests.factories import FAKE_WEBHOOK_SECRET, create_full_rate_table, create_shop, create_user

GATEWAY = FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET)
PAGES = 3
COPIES = 1
BASE_PAISE = 200
PRICE = PAGES * COPIES * BASE_PAISE


@pytest.fixture
def race_engine(test_database: str):
    url = make_url(test_database)
    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()


def _seed(engine) -> tuple[uuid.UUID, uuid.UUID, str]:
    """A customer, a shop and an order, really committed."""
    run_id = uuid.uuid4().hex[:8]
    with Session(engine) as session:
        customer = create_user(session, email=f"race-{run_id}@example.com")
        vendor = create_user(session, email=f"race-vendor-{run_id}@example.com", role="vendor")
        shop = create_shop(session, owner=vendor, name=f"Race Shop {run_id}")
        create_full_rate_table(session, shop, base_paise=BASE_PAISE)
        upload = _upload(session, customer=customer, run_id=run_id)
        order, _payment = order_service.create_order(
            session,
            customer_id=customer.id,
            request=OrderCreateRequest(
                upload_id=upload.id,
                shop_id=shop.id,
                paper_size="A4",
                color=False,
                duplex=False,
                copies=COPIES,
            ),
            idempotency_key=f"race-{run_id}",
            gateway=GATEWAY,
        )
        return customer.id, order.id, run_id


def _upload(session: Session, *, customer, run_id: str) -> Upload:
    upload = Upload(
        customer_id=customer.id,
        file_key=f"uploads/race-{run_id}.pdf",
        original_filename="race.pdf",
        size_bytes=1024,
        sha256="0" * 64,
        page_count=PAGES,
    )
    session.add(upload)
    session.commit()
    return upload


def _payload(provider_order_id: str) -> bytes:
    return json.dumps(
        {
            "event": "order.paid",
            "payload": {
                "payment": {
                    "id": f"pay_race_{uuid.uuid4().hex}",
                    "order_id": provider_order_id,
                    "amount": PRICE,
                    "currency": "INR",
                }
            },
        }
    ).encode()


def _cleanup(engine, customer_id: uuid.UUID, order_id: uuid.UUID, run_id: str) -> None:
    with Session(engine) as session:
        session.execute(delete(OrderEvent).where(OrderEvent.order_id == order_id))
        session.execute(delete(Payment).where(Payment.order_id == order_id))
        session.execute(delete(Order).where(Order.id == order_id))
        session.execute(delete(Upload).where(Upload.file_key == f"uploads/race-{run_id}.pdf"))
        session.execute(
            delete(WebhookEvent).where(WebhookEvent.event_id.like(f"evt_race_{run_id}%"))
        )
        session.execute(
            delete(ShopRate).where(
                ShopRate.shop_id.in_(select(Shop.id).where(Shop.name.like(f"Race Shop {run_id}%")))
            )
        )
        session.execute(delete(Shop).where(Shop.name.like(f"Race Shop {run_id}%")))
        session.execute(delete(User).where(User.email.like(f"race-%{run_id}@example.com")))
        session.commit()


def test_a_capture_is_not_left_behind_when_the_order_goes_terminal(
    race_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The capture and the state change are one operation.

    The order goes terminal on another connection while the payment is
    landing. The money was taken at the provider, so it has to be
    scheduled for a refund. A payment that was captured on its own, with
    no order behind it and no refund scheduled, is money the platform is
    keeping.
    """
    customer_id, order_id, run_id = _seed(race_engine)
    try:
        with Session(race_engine) as session:
            payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
            assert payment is not None
            provider_order_id = payment.provider_order_id
        raw_body = _payload(provider_order_id)

        real_transition = order_service.transition

        def expire_then_transition(session, *, order_id, to_status, actor_type, **kwargs):
            # The order went terminal while the payment was landing. It
            # is another transaction that did it, and it committed, so
            # the payment's transaction cannot undo it.
            other = Session(bind=race_engine)
            try:
                other.execute(update(Order).where(Order.id == order_id).values(status="EXPIRED"))
                other.commit()
            finally:
                other.close()
            return real_transition(
                session, order_id=order_id, to_status=to_status, actor_type=actor_type, **kwargs
            )

        monkeypatch.setattr(payment_service.order_service, "transition", expire_then_transition)

        with Session(race_engine) as session:
            outcome = payment_service.handle_webhook(
                session,
                raw_body=raw_body,
                signature=GATEWAY.sign(raw_body),
                event_id=f"evt_race_{run_id}",
                gateway=GATEWAY,
            )

        assert outcome == "refund_pending"
        with Session(race_engine) as session:
            payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
            assert payment is not None
            assert payment.status == "REFUND_PENDING"
            assert payment.refund_next_attempt_at is not None
            order = session.get(Order, order_id)
            assert order is not None
            assert order.status == "EXPIRED"
    finally:
        _cleanup(race_engine, customer_id, order_id, run_id)


def test_a_delivery_that_failed_is_not_spent(race_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure before the effect leaves the event id usable.

    The provider retries a delivery it was told failed. If the event id
    were spent by the failed attempt, the retry would be told the event
    had already been applied, and the order would never be paid.
    """
    customer_id, order_id, run_id = _seed(race_engine)
    try:
        with Session(race_engine) as session:
            payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
            assert payment is not None
            provider_order_id = payment.provider_order_id
        raw_body = _payload(provider_order_id)

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("the database was busy")

        monkeypatch.setattr(payment_service, "_handle_order_paid", explode)

        with Session(race_engine) as session, pytest.raises(RuntimeError):
            payment_service.handle_webhook(
                session,
                raw_body=raw_body,
                signature=GATEWAY.sign(raw_body),
                event_id=f"evt_race_{run_id}",
                gateway=GATEWAY,
            )

        monkeypatch.undo()

        with Session(race_engine) as session:
            outcome = payment_service.handle_webhook(
                session,
                raw_body=raw_body,
                signature=GATEWAY.sign(raw_body),
                event_id=f"evt_race_{run_id}",
                gateway=GATEWAY,
            )

        assert outcome == "paid"
        with Session(race_engine) as session:
            order = session.get(Order, order_id)
            assert order is not None
            assert order.status == "PAID"
    finally:
        _cleanup(race_engine, customer_id, order_id, run_id)


def test_the_transition_refusal_is_not_swallowed(
    race_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A capture that could not be applied is not an applied capture.

    The order is still waiting for its payment, so the money was taken at
    the provider but the order was not paid. The delivery is answered
    with a status that says "try again", and the event is not recorded
    as applied, so the retry can still apply it.
    """
    customer_id, order_id, run_id = _seed(race_engine)
    try:
        with Session(race_engine) as session:
            payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
            assert payment is not None
            provider_order_id = payment.provider_order_id
        raw_body = _payload(provider_order_id)

        def refuse_the_transition(session, **kwargs):
            raise InvalidTransition("The order is no longer waiting for a payment")

        monkeypatch.setattr(payment_service.order_service, "transition", refuse_the_transition)

        with Session(race_engine) as session, pytest.raises(Exception) as raised:
            payment_service.handle_webhook(
                session,
                raw_body=raw_body,
                signature=GATEWAY.sign(raw_body),
                event_id=f"evt_race_{run_id}",
                gateway=GATEWAY,
            )

        assert getattr(raised.value, "status_code", None) == 503
        with Session(race_engine) as session:
            payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
            assert payment is not None
            assert payment.status != "CAPTURED"
            order = session.get(Order, order_id)
            assert order is not None
            assert order.status == "PENDING_PAYMENT"
    finally:
        _cleanup(race_engine, customer_id, order_id, run_id)
