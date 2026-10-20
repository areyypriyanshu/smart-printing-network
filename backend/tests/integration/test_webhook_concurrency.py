"""Concurrent webhook delivery.

The payment provider can deliver the same event twice, and it can deliver
two copies at the same moment. Both have to end with exactly one capture,
one transition and one event row.

These tests use real connections and real threads, because a sequential
test cannot show a race. They commit their own data, so they do not use
the shared `db_session` fixture, and they clean up after themselves.
"""

import json
import threading
import uuid

import pytest
from app.gateways.payments import FakeGateway
from app.models import (
    Order,
    OrderEvent,
    Payment,
    RefreshToken,
    Shop,
    ShopRate,
    Upload,
    User,
    WebhookEvent,
)
from app.schemas.order import OrderCreateRequest
from app.services import order_service, payment_service
from sqlalchemy import create_engine, delete, select
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
        order, payment = order_service.create_order(
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
        session.execute(delete(RefreshToken).where(RefreshToken.user_id == customer_id))
        session.execute(delete(User).where(User.email.like(f"race-%{run_id}@example.com")))
        session.commit()


def _deliver_in_parallel(
    engine, raw_body: bytes, event_ids: list[str]
) -> tuple[list[str], list[BaseException]]:
    outcomes: list[str] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(len(event_ids))

    def deliver(event_id: str) -> None:
        try:
            barrier.wait()
            with Session(engine) as session:
                outcomes.append(
                    payment_service.handle_webhook(
                        session,
                        raw_body=raw_body,
                        signature=GATEWAY.sign(raw_body),
                        event_id=event_id,
                        gateway=GATEWAY,
                    )
                )
        except BaseException as exc:  # noqa: BLE001 - the test asserts on it
            errors.append(exc)

    threads = [threading.Thread(target=deliver, args=(event_id,)) for event_id in event_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return outcomes, errors


def _assert_single_capture(engine, order_id: uuid.UUID) -> None:
    with Session(engine) as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "PAID"
        payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
        assert payment is not None
        assert payment.status == "CAPTURED"
        paid_events = list(
            session.scalars(
                select(OrderEvent).where(
                    OrderEvent.order_id == order_id,
                    OrderEvent.to_status == "PAID",
                )
            )
        )
        assert len(paid_events) == 1, "the order must be marked paid exactly once"


def test_two_threads_delivering_the_same_event_capture_once(race_engine) -> None:
    customer_id, order_id, run_id = _seed(race_engine)
    try:
        with Session(race_engine) as session:
            payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
            assert payment is not None
            provider_order_id = payment.provider_order_id
        raw_body = _payload(provider_order_id)
        event_id = f"evt_race_{run_id}"

        outcomes, errors = _deliver_in_parallel(race_engine, raw_body, [event_id, event_id])

        assert errors == []
        assert len(outcomes) == 2
        assert "paid" in outcomes
        assert "duplicate" in outcomes
        _assert_single_capture(race_engine, order_id)

        with Session(race_engine) as session:
            rows = list(
                session.scalars(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
            )
            assert len(rows) == 1
    finally:
        _cleanup(race_engine, customer_id, order_id, run_id)


def test_two_different_events_for_the_same_payment_capture_once(race_engine) -> None:
    customer_id, order_id, run_id = _seed(race_engine)
    try:
        with Session(race_engine) as session:
            payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
            assert payment is not None
            provider_order_id = payment.provider_order_id
        raw_body = _payload(provider_order_id)
        event_ids = [f"evt_race_{run_id}_a", f"evt_race_{run_id}_b"]

        outcomes, errors = _deliver_in_parallel(race_engine, raw_body, event_ids)

        assert errors == []
        assert len(outcomes) == 2
        # One delivery pays the order. The other finds it already paid,
        # which is what two events for one payment mean together.
        assert "paid" in outcomes
        assert "already_paid" in outcomes
        _assert_single_capture(race_engine, order_id)
    finally:
        _cleanup(race_engine, customer_id, order_id, run_id)
