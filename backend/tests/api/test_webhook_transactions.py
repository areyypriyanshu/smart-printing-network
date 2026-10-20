"""What the webhook route does with a delivery that cannot be applied.

The provider retries a delivery it was told failed. If the application
records the event id before it has applied the effect, then a delivery
that failed for a reason of its own is spent: the retry arrives, sees the
id, and is told "already done". The order is never paid, and the customer
has paid.

These are the tests for that, and for the money that is taken at the
provider when the order has already gone away.
"""

import json
import uuid

from app.errors import Conflict
from app.models import Order, Payment, WebhookEvent
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    FAKE_WEBHOOK_SECRET,
    create_full_rate_table,
    create_shop,
    create_upload_row,
    create_user,
    login_headers,
)

ORDERS = "/api/v1/orders"
WEBHOOK = "/api/v1/webhooks/razorpay"
BASE_PAISE = 200
PAGES = 5
COPIES = 2
PRICE = PAGES * COPIES * BASE_PAISE

from app.gateways.payments import FakeGateway  # noqa: E402

GATEWAY = FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET)


def _seed(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop, base_paise=BASE_PAISE)
    upload = create_upload_row(session, customer=customer, page_count=PAGES)
    return customer.id, shop.id, upload.id


def _create_order(client: TestClient, session: Session) -> dict:
    _customer_id, shop_id, upload_id = _seed(session)
    headers = login_headers(client, "customer@example.com")
    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json={
            "upload_id": str(upload_id),
            "shop_id": str(shop_id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": COPIES,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _paid_payload(provider_order_id: str, *, amount: int) -> bytes:
    return json.dumps(
        {
            "event": "order.paid",
            "payload": {
                "payment": {
                    "id": "pay_fake_1",
                    "order_id": provider_order_id,
                    "amount": amount,
                    "currency": "INR",
                }
            },
        }
    ).encode()


def _post_webhook(client: TestClient, raw_body: bytes, *, event_id: str):
    return client.post(
        WEBHOOK,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Event-Id": event_id,
            "X-Razorpay-Signature": GATEWAY.sign(raw_body),
        },
    )


def test_a_delivery_that_failed_is_not_spent(
    client_that_reports_failures: TestClient, db_session: Session, monkeypatch
) -> None:
    """A failure before the effect must leave the event id usable.

    The provider retries a delivery it was told failed. If the event id
    were spent by the failed attempt, the retry would be told the event
    had already been applied, and the order would never be paid.
    """
    created = _create_order(client_that_reports_failures, db_session)
    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE)

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the database was busy")

    from app.services import payment_service

    monkeypatch.setattr(payment_service, "_handle_order_paid", explode)
    failed = _post_webhook(client_that_reports_failures, raw_body, event_id="evt_retry")
    assert failed.status_code == 500, failed.text

    monkeypatch.undo()
    retried = _post_webhook(client_that_reports_failures, raw_body, event_id="evt_retry")

    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "paid"
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    assert order.status == "PAID"


def test_a_delivery_that_was_applied_is_answered_as_a_duplicate(
    client: TestClient, db_session: Session
) -> None:
    created = _create_order(client, db_session)
    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE)

    first = _post_webhook(client, raw_body, event_id="evt_same")
    second = _post_webhook(client, raw_body, event_id="evt_same")

    assert first.json()["status"] == "paid"
    assert second.json()["status"] == "duplicate"
    event = db_session.scalar(select(WebhookEvent).where(WebhookEvent.event_id == "evt_same"))
    assert event is not None
    assert event.processed_at is not None


def test_a_late_payment_is_scheduled_for_a_refund(client: TestClient, db_session: Session) -> None:
    """A payment that lands after the order expired has to go back.

    The refund job selects on the next-attempt time, so a row that is
    waiting for a refund but has no time set would never be picked up,
    and the money would stay with the platform for ever.
    """
    created = _create_order(client, db_session)
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    order.status = "EXPIRED"
    db_session.commit()

    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE)

    response = _post_webhook(client, raw_body, event_id="evt_late")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "refund_pending"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "REFUND_PENDING"
    assert payment.refund_next_attempt_at is not None


def test_a_payment_that_lands_on_a_cancelled_order_is_scheduled_for_a_refund(
    client: TestClient, db_session: Session
) -> None:
    created = _create_order(client, db_session)
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    order.status = "CANCELLED"
    db_session.commit()

    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE)

    response = _post_webhook(client, raw_body, event_id="evt_cancelled")

    assert response.json()["status"] == "refund_pending"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "REFUND_PENDING"
    assert payment.refund_next_attempt_at is not None


def test_a_transition_that_fails_is_answered_so_the_provider_retries(
    client_that_reports_failures: TestClient, db_session: Session, monkeypatch
) -> None:
    """A capture that could not be applied is not an applied capture.

    The order is still waiting for its payment, so the money was taken at
    the provider but the order was not paid. The delivery is answered
    with a status that says "try again", and the event is not recorded
    as applied, so the retry can still apply it.
    """
    created = _create_order(client_that_reports_failures, db_session)
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE)

    from app.services import payment_service

    def refuse_the_transition(session, **kwargs):  # type: ignore[no-untyped-def]
        raise Conflict("The order is busy")

    monkeypatch.setattr(payment_service.order_service, "transition", refuse_the_transition)

    response = _post_webhook(client_that_reports_failures, raw_body, event_id="evt_busy")

    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "PAYMENT_NOT_APPLIED"
    db_session.refresh(order)
    assert order.status == "PENDING_PAYMENT"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status != "CAPTURED"
