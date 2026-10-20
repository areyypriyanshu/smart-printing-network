import json
import uuid

import pytest
from app.gateways.payments import FakeGateway
from app.models import Order, OrderEvent, Payment, WebhookEvent
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
SIMULATE = "/api/v1/testing/simulate-payment"
BASE_PAISE = 200
PAGES = 5
COPIES = 2
PRICE = PAGES * COPIES * BASE_PAISE
GATEWAY = FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET)


def _seed(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop, base_paise=BASE_PAISE)
    upload = create_upload_row(session, customer=customer, page_count=PAGES)
    return customer.id, shop.id, upload.id


def _create_order_for(
    client: TestClient,
    session: Session,
    *,
    email: str,
    idempotency_key: str,
) -> dict:
    """An order for a customer of its own, so two orders can exist at once."""
    customer = create_user(session, email=email)
    vendor = create_user(session, email=f"vendor-{email}", role="vendor")
    shop = create_shop(session, owner=vendor, name=f"Shop for {email}")
    create_full_rate_table(session, shop, base_paise=BASE_PAISE)
    upload = create_upload_row(session, customer=customer, page_count=PAGES)
    headers = login_headers(client, email)
    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": idempotency_key},
        json={
            "upload_id": str(upload.id),
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": COPIES,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


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


def _paid_payload(
    provider_order_id: str,
    *,
    amount: int,
    currency: str = "INR",
    payment_id: str = "pay_fake_1",
) -> bytes:
    return json.dumps(
        {
            "event": "order.paid",
            "payload": {
                "payment": {
                    "id": payment_id,
                    "order_id": provider_order_id,
                    "amount": amount,
                    "currency": currency,
                }
            },
        }
    ).encode()


def _post_webhook(
    client: TestClient, raw_body: bytes, *, event_id: str, signature: str | None = None
):
    return client.post(
        WEBHOOK,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Event-Id": event_id,
            "X-Razorpay-Signature": signature if signature is not None else GATEWAY.sign(raw_body),
        },
    )


def test_webhook_with_a_forged_signature_is_rejected(
    client: TestClient, db_session: Session
) -> None:
    created = _create_order(client, db_session)
    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE)

    response = _post_webhook(client, raw_body, event_id="evt_1", signature="0" * 64)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    assert order.status == "PENDING_PAYMENT"


def test_signed_webhook_marks_the_order_paid(client: TestClient, db_session: Session) -> None:
    created = _create_order(client, db_session)
    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE)

    response = _post_webhook(client, raw_body, event_id="evt_1")

    assert response.status_code == 200
    assert response.json()["status"] == "paid"
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    assert order.status == "PAID"
    assert order.paid_at is not None
    assert order.pickup_code is not None
    assert len(order.pickup_code) == 6
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CAPTURED"
    assert payment.provider_payment_id == "pay_fake_1"


def test_duplicate_webhook_delivery_is_a_no_op(client: TestClient, db_session: Session) -> None:
    created = _create_order(client, db_session)
    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE)

    first = _post_webhook(client, raw_body, event_id="evt_1")
    second = _post_webhook(client, raw_body, event_id="evt_1")

    assert first.status_code == 200
    assert first.json()["status"] == "paid"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    events = list(
        db_session.scalars(
            select(OrderEvent).where(OrderEvent.order_id == uuid.UUID(created["order"]["id"]))
        )
    )
    assert [event.to_status for event in events] == ["PENDING_PAYMENT", "PAID"]
    assert (
        len(list(db_session.scalars(select(WebhookEvent).where(WebhookEvent.event_id == "evt_1"))))
        == 1
    )


def test_webhook_with_a_wrong_amount_does_not_mark_the_order_paid(
    client: TestClient, db_session: Session
) -> None:
    created = _create_order(client, db_session)
    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE + 1)

    response = _post_webhook(client, raw_body, event_id="evt_1")

    assert response.status_code == 200
    assert response.json()["status"] == "amount_mismatch"
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    assert order.status == "PENDING_PAYMENT"
    assert order.pickup_code is None


def test_webhook_with_a_wrong_currency_does_not_mark_the_order_paid(
    client: TestClient, db_session: Session
) -> None:
    created = _create_order(client, db_session)
    provider_order_id = created["payment"]["provider_order_id"]
    raw_body = _paid_payload(provider_order_id, amount=PRICE, currency="USD")

    response = _post_webhook(client, raw_body, event_id="evt_1")

    assert response.status_code == 200
    assert response.json()["status"] == "amount_mismatch"
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    assert order.status == "PENDING_PAYMENT"


def test_late_payment_on_an_expired_order_queues_a_refund(
    client: TestClient, db_session: Session
) -> None:
    created = _create_order(client, db_session)
    order_id = uuid.UUID(created["order"]["id"])
    provider_order_id = created["payment"]["provider_order_id"]
    order = db_session.get(Order, order_id)
    assert order is not None
    from app.services import order_service

    order_service.transition(
        db_session, order_id=order_id, to_status="EXPIRED", actor_type="system"
    )
    raw_body = _paid_payload(provider_order_id, amount=PRICE)

    response = _post_webhook(client, raw_body, event_id="evt_late")

    assert response.status_code == 200
    assert response.json()["status"] == "refund_pending"
    db_session.refresh(order)
    assert order.status == "EXPIRED"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order_id))
    assert payment is not None
    assert payment.status == "REFUND_PENDING"


def test_unknown_webhook_event_is_recorded_and_ignored(
    client: TestClient, db_session: Session
) -> None:
    _create_order(client, db_session)
    raw_body = json.dumps({"event": "something.else", "payload": {}}).encode()

    response = _post_webhook(client, raw_body, event_id="evt_other")

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    event = db_session.get(WebhookEvent, "evt_other")
    assert event is not None
    assert event.processed_at is not None


def test_webhook_without_an_event_id_is_rejected(client: TestClient, db_session: Session) -> None:
    _create_order(client, db_session)
    raw_body = json.dumps({"event": "order.paid"}).encode()

    response = client.post(
        WEBHOOK,
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": GATEWAY.sign(raw_body),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_simulate_payment_endpoint_marks_the_order_paid(
    client: TestClient, db_session: Session
) -> None:
    created = _create_order(client, db_session)
    order_id = created["order"]["id"]

    response = client.post(
        SIMULATE, json={"order_id": order_id}, headers=login_headers(client, "customer@example.com")
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paid"
    order = db_session.get(Order, uuid.UUID(order_id))
    assert order is not None
    assert order.status == "PAID"
    assert order.pickup_code is not None


def test_simulate_payment_needs_a_token(client: TestClient, db_session: Session) -> None:
    """The testing route marks an order paid, so it is not anonymous."""
    created = _create_order(client, db_session)

    response = client.post(SIMULATE, json={"order_id": created["order"]["id"]})

    assert response.status_code == 401
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    assert order.status == "PENDING_PAYMENT"


def test_simulate_payment_does_not_pay_another_customers_order(
    client: TestClient, db_session: Session
) -> None:
    """The route is bound to the caller, so it cannot reach another's order."""
    created = _create_order(client, db_session)
    create_user(db_session, email="other@example.com")

    response = client.post(
        SIMULATE,
        json={"order_id": created["order"]["id"]},
        headers=login_headers(client, "other@example.com"),
    )

    assert response.status_code == 404
    order = db_session.get(Order, uuid.UUID(created["order"]["id"]))
    assert order is not None
    assert order.status == "PENDING_PAYMENT"


def test_simulate_payment_is_disabled_when_the_testing_surface_is_off(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_order(client, db_session)
    monkeypatch.setattr(
        "app.routers.webhooks.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "env": "local",
                "payment_provider": "fake",
                "testing_endpoints_enabled": False,
            },
        )(),
    )

    response = client.post(
        SIMULATE,
        json={"order_id": created["order"]["id"]},
        headers=login_headers(client, "customer@example.com"),
    )

    assert response.status_code == 404


def test_simulate_payment_is_disabled_in_production(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create_order(client, db_session)
    monkeypatch.setattr(
        "app.routers.webhooks.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "env": "production",
                "payment_provider": "fake",
                "testing_endpoints_enabled": True,
            },
        )(),
    )

    response = client.post(
        SIMULATE,
        json={"order_id": created["order"]["id"]},
        headers=login_headers(client, "customer@example.com"),
    )

    assert response.status_code == 404


def _refund_payload(provider_payment_id: str, *, refund_id: str = "rfnd_1") -> bytes:
    return json.dumps(
        {
            "event": "refund.processed",
            "payload": {"refund": {"id": refund_id, "payment_id": provider_payment_id}},
        }
    ).encode()


def test_refund_processed_marks_the_payment_refunded(
    client: TestClient, db_session: Session
) -> None:
    created = _create_order(client, db_session)
    provider_order_id = created["payment"]["provider_order_id"]
    paid = _post_webhook(
        client, _paid_payload(provider_order_id, amount=PRICE), event_id="evt_paid"
    )
    assert paid.status_code == 200

    raw_body = _refund_payload("pay_fake_1")
    response = _post_webhook(client, raw_body, event_id="evt_refund")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "refunded"
    payment = db_session.scalar(
        select(Payment).where(Payment.provider_order_id == provider_order_id)
    )
    assert payment is not None
    assert payment.status == "REFUNDED"
    assert payment.refund_id == "rfnd_1"


def test_refund_processed_for_an_unknown_payment_is_ignored(
    client: TestClient, db_session: Session
) -> None:
    _create_order(client, db_session)

    raw_body = _refund_payload("pay_does_not_exist")
    response = _post_webhook(client, raw_body, event_id="evt_refund_unknown")

    assert response.status_code == 200
    assert response.json()["status"] == "unknown_payment"


def test_a_webhook_with_a_broken_body_is_rejected(client: TestClient, db_session: Session) -> None:
    _create_order(client, db_session)

    response = _post_webhook(client, b"{not json", event_id="evt_broken")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_payment_for_an_unknown_order_is_ignored(client: TestClient, db_session: Session) -> None:
    _create_order(client, db_session)

    raw_body = _paid_payload("fake_order_does_not_exist", amount=PRICE)
    response = _post_webhook(client, raw_body, event_id="evt_unknown_order")

    assert response.status_code == 200
    assert response.json()["status"] == "unknown_order"


def test_a_second_order_cannot_claim_the_same_provider_payment_id(
    client: TestClient, db_session: Session
) -> None:
    first = _create_order(client, db_session)
    second = _create_order_for(
        client, db_session, email="second@example.com", idempotency_key="key-2"
    )
    paid = _post_webhook(
        client,
        _paid_payload(first["payment"]["provider_order_id"], amount=PRICE),
        event_id="evt_paid_first",
    )
    assert paid.status_code == 200

    # The same provider payment id, but for a different order. The first
    # order already owns it, so this one must not be captured.
    raw_body = _paid_payload(
        second["payment"]["provider_order_id"], amount=PRICE, payment_id="pay_fake_1"
    )
    response = _post_webhook(client, raw_body, event_id="evt_paid_second")

    assert response.status_code == 200
    assert response.json()["status"] == "duplicate_payment"
    second_order = db_session.get(Order, uuid.UUID(second["order"]["id"]))
    assert second_order is not None
    assert second_order.status == "PENDING_PAYMENT"


def test_a_delivery_without_an_event_id_is_refused(client: TestClient, db_session: Session) -> None:
    """A delivery that cannot be deduplicated is not accepted.

    The event id is required, and the contract says so, so a delivery
    without one is a validation error rather than something the route
    has to notice for itself.
    """
    response = client.post(
        WEBHOOK,
        content=b'{"event":"order.paid"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_delivery_with_an_empty_event_id_is_refused(
    client: TestClient, db_session: Session
) -> None:
    """An event id that is there but empty is the same as none at all."""
    response = client.post(
        WEBHOOK,
        content=b'{"event":"order.paid"}',
        headers={"Content-Type": "application/json", "X-Razorpay-Event-Id": ""},
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
