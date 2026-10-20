"""Paying at the shop: the customer books the job and pays in cash.

The whole point of this path is that it behaves like the online path in
every way except when the money moves. The same order, the same pickup
code, the same vendor queue, the same collect endpoint, the same audit
trail. These tests are the observable version of that claim.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.models import Order, OrderEvent, Payment
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    FAKE_WEBHOOK_SECRET,
    create_full_rate_table,
    create_paid_order,
    create_reserved_order,
    create_shop,
    create_upload_row,
    create_user,
    login_headers,
)

ORDERS = "/api/v1/orders"
QUEUE = "/api/v1/vendor/queue"
CUSTOMER_EMAIL = "customer@example.com"
VENDOR_EMAIL = "vendor@example.com"
OTHER_VENDOR_EMAIL = "other-vendor@example.com"


def _seed(session: Session) -> tuple[object, object]:
    customer = create_user(session, email=CUSTOMER_EMAIL)
    vendor = create_user(session, email=VENDOR_EMAIL, role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    return customer, shop


def _book(
    client: TestClient,
    session: Session,
    *,
    payment_method: str = "at_store",
    email: str = CUSTOMER_EMAIL,
    idempotency_key: str = "cash-1",
    copies: int = 1,
) -> dict:
    """Book an order through the API, the way a customer does."""
    customer = create_user(session, email=email)
    vendor = create_user(session, email=f"vendor-{email}", role="vendor")
    shop = create_shop(session, owner=vendor, name=f"Shop for {email}")
    create_full_rate_table(session, shop)
    upload = create_upload_row(session, customer=customer, page_count=1)
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
            "copies": copies,
            "payment_method": payment_method,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _work_the_order(client: TestClient, order: Order, headers: dict[str, str]) -> None:
    """Take a job the way a shop does: accept, start, then ready."""
    for action in ("accept", "start", "ready"):
        response = client.post(
            f"/api/v1/vendor/orders/{order.id}/{action}", headers=headers, json={}
        )
        assert response.status_code == 200, response.text


def test_booking_with_pay_at_the_shop_reserves_the_order(
    client: TestClient, db_session: Session
) -> None:
    """The order is booked, not paid, and it already has its code."""
    body = _book(client, db_session)

    assert body["order"]["status"] == "RESERVED"
    assert body["order"]["payment_method"] == "at_store"
    assert body["order"]["pickup_code"] is not None
    assert len(body["order"]["pickup_code"]) == 6
    assert body["order"]["pickup_code"].isdigit()
    assert body["order"]["paid_at"] is None


def test_a_cash_order_has_a_cash_payment_that_is_not_captured(
    client: TestClient, db_session: Session
) -> None:
    body = _book(client, db_session)

    assert body["payment"]["provider"] == "cash"
    assert body["payment"]["key_id"] is None

    payment = db_session.scalar(
        select(Payment).where(Payment.order_id == uuid.UUID(body["order"]["id"]))
    )
    assert payment is not None
    assert payment.provider == "cash"
    assert payment.status == "CREATED"
    assert payment.amount_paise == body["order"]["price_paise"]


def test_booking_online_is_unchanged(client: TestClient, db_session: Session) -> None:
    """The default method is the one that always worked."""
    body = _book(client, db_session, payment_method="online")

    assert body["order"]["status"] == "PENDING_PAYMENT"
    assert body["order"]["payment_method"] == "online"
    assert body["order"]["pickup_code"] is None
    assert body["payment"]["provider"] == "fake"


def test_booking_online_without_saying_so_is_unchanged(
    client: TestClient, db_session: Session
) -> None:
    """A client that does not know about cash keeps working."""
    customer = create_user(db_session, email=CUSTOMER_EMAIL)
    vendor = create_user(db_session, email=VENDOR_EMAIL, role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    upload = create_upload_row(db_session, customer=customer, page_count=1)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json={
            "upload_id": str(upload.id),
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["order"]["status"] == "PENDING_PAYMENT"
    assert response.json()["order"]["payment_method"] == "online"


def test_an_unknown_payment_method_is_rejected(client: TestClient, db_session: Session) -> None:
    """The method is a closed set."""
    customer = create_user(db_session, email=CUSTOMER_EMAIL)
    vendor = create_user(db_session, email=VENDOR_EMAIL, role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    upload = create_upload_row(db_session, customer=customer, page_count=1)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json={
            "upload_id": str(upload.id),
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
            "payment_method": "cheque",
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_paying_at_the_shop_is_refused_when_it_is_switched_off(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    """The feature is off by default, so a fresh deployment cannot use it."""
    customer, shop = _seed(db_session)
    upload = create_upload_row(db_session, customer=customer, page_count=1)
    monkeypatch.setattr(get_settings(), "cash_at_store_enabled", False)

    response = client.post(
        ORDERS,
        headers={**login_headers(client, CUSTOMER_EMAIL), "Idempotency-Key": "key-1"},
        json={
            "upload_id": str(upload.id),
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
            "payment_method": "at_store",
        },
    )

    # The feature is checked before anything else, so the request is
    # refused for that reason and not because the upload does not exist.
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "CASH_PAYMENT_DISABLED"


def test_the_shop_sees_a_cash_order_in_its_queue(client: TestClient, db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(QUEUE, headers=headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(order.id)]
    assert items[0]["payment_method"] == "at_store"
    assert items[0]["paid_at"] is None


def test_a_cash_order_does_not_sort_last_in_the_queue(
    client: TestClient, db_session: Session
) -> None:
    """It has no paid_at, so it must not be queued by paid_at.

    The queue is ordered by when the order was reserved. A cash order
    reserved first is served first, even though it has no paid_at at all.
    """
    customer, shop = _seed(db_session)
    later = create_paid_order(db_session, customer=customer, shop=shop, copies=2)
    earlier = create_reserved_order(
        db_session,
        customer=customer,
        shop=shop,
        reserved_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(QUEUE, headers=headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert earlier.reserved_at is not None and later.reserved_at is not None
    assert earlier.reserved_at < later.reserved_at
    assert [item["id"] for item in items] == [str(earlier.id), str(later.id)]


def test_the_shop_can_work_a_cash_order_through_the_usual_endpoints(
    client: TestClient, db_session: Session
) -> None:
    """No new endpoint. The same ones the online flow uses."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    for action, expected in (
        ("accept", "ACCEPTED"),
        ("start", "PRINTING"),
        ("ready", "READY"),
    ):
        response = client.post(
            f"/api/v1/vendor/orders/{order.id}/{action}", headers=headers, json={}
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected

    response = client.post(
        f"/api/v1/vendor/orders/{order.id}/collect",
        headers=headers,
        json={"code": order.pickup_code},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COLLECTED"


def test_collecting_a_cash_order_captures_the_payment(
    client: TestClient, db_session: Session
) -> None:
    """The money changed hands, and the record says so."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    _work_the_order(client, order, headers)

    response = client.post(
        f"/api/v1/vendor/orders/{order.id}/collect",
        headers=headers,
        json={"code": order.pickup_code},
    )

    assert response.status_code == 200, response.text
    db_session.refresh(order)
    assert order.status == "COLLECTED"
    assert order.paid_at is not None
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CAPTURED"
    assert payment.provider_payment_id is not None


def test_collecting_a_cash_order_records_the_shop_in_the_audit_trail(
    client: TestClient, db_session: Session
) -> None:
    """The event trail is the evidence a settlement would be built on."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    _work_the_order(client, order, headers)

    client.post(
        f"/api/v1/vendor/orders/{order.id}/collect",
        headers=headers,
        json={"code": order.pickup_code},
    )

    events = list(
        db_session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == order.id)
            .order_by(OrderEvent.at.asc(), OrderEvent.id.asc())
        )
    )
    assert [event.to_status for event in events] == [
        "RESERVED",
        "ACCEPTED",
        "PRINTING",
        "READY",
        "COLLECTED",
    ]
    assert events[0].actor_type == "customer"
    assert events[-1].actor_type == "vendor"


def test_the_pickup_code_does_not_change_when_the_order_is_collected(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    code = order.pickup_code
    headers = login_headers(client, VENDOR_EMAIL)
    _work_the_order(client, order, headers)

    client.post(
        f"/api/v1/vendor/orders/{order.id}/collect",
        headers=headers,
        json={"code": code},
    )

    db_session.refresh(order)
    assert order.pickup_code == code


def test_the_wrong_code_is_refused_for_a_cash_order(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.post(
        f"/api/v1/vendor/orders/{order.id}/collect",
        headers=headers,
        json={"code": "000000"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "PICKUP_CODE_INVALID"
    db_session.refresh(order)
    assert order.status == "RESERVED"


def test_the_attempt_limit_applies_to_a_cash_order(client: TestClient, db_session: Session) -> None:
    """A shop cannot brute force the code of a cash order either."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    for _ in range(5):
        response = client.post(
            f"/api/v1/vendor/orders/{order.id}/collect",
            headers=headers,
            json={"code": "000000"},
        )
        assert response.status_code == 400, response.text

    response = client.post(
        f"/api/v1/vendor/orders/{order.id}/collect",
        headers=headers,
        json={"code": "000000"},
    )

    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_a_shop_cannot_collect_a_cash_order_of_another_shop(
    client: TestClient, db_session: Session
) -> None:
    """404, not 403. The response must not confirm the order exists."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    create_user(db_session, email=OTHER_VENDOR_EMAIL, role="vendor")
    headers = login_headers(client, OTHER_VENDOR_EMAIL)

    response = client.post(
        f"/api/v1/vendor/orders/{order.id}/collect",
        headers=headers,
        json={"code": order.pickup_code},
    )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_customer_cannot_collect_their_own_cash_order(
    client: TestClient, db_session: Session
) -> None:
    """Only the shop hands the printout over."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(
        f"/api/v1/vendor/orders/{order.id}/collect",
        headers=headers,
        json={"code": order.pickup_code},
    )

    assert response.status_code in (403, 404), response.text
    db_session.refresh(order)
    assert order.status == "RESERVED"


def test_rejecting_a_cash_order_queues_no_refund(client: TestClient, db_session: Session) -> None:
    """No money was taken, so nothing goes back."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.post(
        f"/api/v1/vendor/orders/{order.id}/reject",
        headers=headers,
        json={"reason": "too busy today"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REJECTED"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"
    assert payment.refund_next_attempt_at is None


def test_a_cash_order_is_never_marked_paid_by_a_webhook(
    client: TestClient, db_session: Session
) -> None:
    """Only the webhook marks an online order paid, and it cannot reach here."""
    import json

    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    payload = json.dumps(
        {
            "event": "order.paid",
            "payload": {
                "payment": {
                    "id": "pay_cash_1",
                    "order_id": payment.provider_order_id,
                    "amount": order.price_paise,
                    "currency": "INR",
                }
            },
        }
    ).encode()
    from app.gateways.payments import FakeGateway

    signature = FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET).sign(payload)

    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=payload,
        headers={
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": "evt_cash_1",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "already_paid"
    db_session.refresh(order)
    assert order.status == "RESERVED"
    assert order.paid_at is None
    db_session.refresh(payment)
    assert payment.status == "CREATED"


def test_the_simulated_payment_endpoint_does_not_pay_a_cash_order(
    client: TestClient, db_session: Session
) -> None:
    """The local dev tool cannot mark a cash order paid either."""
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)

    response = client.post(
        "/api/v1/testing/simulate-payment",
        json={"order_id": str(order.id)},
        headers=login_headers(client, CUSTOMER_EMAIL),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "already_paid"
    db_session.refresh(order)
    assert order.status == "RESERVED"
    assert order.paid_at is None


def test_the_customer_sees_the_cash_order_as_reserved(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.get(f"{ORDERS}/{order.id}", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["order"]["status"] == "RESERVED"
    assert response.json()["order"]["payment_method"] == "at_store"
    assert response.json()["order"]["pickup_code"] == order.pickup_code


def test_a_customer_can_cancel_a_cash_order_before_the_shop_accepts(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(f"{ORDERS}/{order.id}/cancel", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"
