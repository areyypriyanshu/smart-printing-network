import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models import Payment
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_reserved_order,
    create_shop,
    create_unpaid_order,
    create_user,
    login_headers,
)

QUEUE = "/api/v1/vendor/queue"
VENDOR_EMAIL = "vendor@example.com"
OTHER_VENDOR_EMAIL = "other-vendor@example.com"
CUSTOMER_EMAIL = "customer@example.com"


def _seed(session: Session) -> tuple[object, object, object]:
    customer = create_user(session, email=CUSTOMER_EMAIL)
    vendor = create_user(session, email=VENDOR_EMAIL, role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    other_vendor = create_user(session, email=OTHER_VENDOR_EMAIL, role="vendor")
    other_shop = create_shop(session, owner=other_vendor, name="Other Shop")
    create_full_rate_table(session, other_shop)
    return customer, shop, other_shop


def _order_path(order_id: uuid.UUID) -> str:
    return f"/api/v1/vendor/orders/{order_id}"


def test_queue_lists_reserved_orders_oldest_reservation_first(
    client: TestClient, db_session: Session
) -> None:
    customer, shop, _ = _seed(db_session)
    first = create_reserved_order(
        db_session,
        customer=customer,
        shop=shop,
        copies=1,
        reserved_at=datetime.now(UTC) - timedelta(minutes=2),
    )
    second = create_reserved_order(db_session, customer=customer, shop=shop, copies=2)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(QUEUE, headers=headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(first.id), str(second.id)]


def test_queue_never_returns_the_pickup_code(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(QUEUE, headers=headers)

    assert response.status_code == 200
    assert "pickup_code" not in response.json()["items"][0]
    assert str(order.pickup_code) not in response.text


def test_queue_hides_orders_of_another_shop(client: TestClient, db_session: Session) -> None:
    customer, _shop, other_shop = _seed(db_session)
    create_reserved_order(db_session, customer=customer, shop=other_shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(QUEUE, headers=headers)

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_queue_hides_a_historical_order_that_was_never_paid(
    client: TestClient, db_session: Session
) -> None:
    """A row left in PENDING_PAYMENT was never the shop's work."""
    customer, shop, _ = _seed(db_session)
    create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    order = create_unpaid_order(db_session, customer=customer, shop=shop)

    response = client.get(QUEUE, headers=headers)

    assert response.status_code == 200
    assert all(item["id"] != str(order.id) for item in response.json()["items"])


def test_queue_is_forbidden_for_a_customer(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.get(QUEUE, headers=headers)

    assert response.status_code == 403


def test_queue_requires_authentication(client: TestClient, db_session: Session) -> None:
    _seed(db_session)

    response = client.get(QUEUE)

    assert response.status_code == 401


def test_vendor_order_detail_hides_another_shops_order(
    client: TestClient, db_session: Session
) -> None:
    customer, _shop, other_shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=other_shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(_order_path(order.id), headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_vendor_order_detail_never_exposes_the_pickup_code(
    client: TestClient, db_session: Session
) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(_order_path(order.id), headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert "pickup_code" not in body["order"]
    assert str(order.pickup_code) not in response.text
    assert body["order"]["status"] == "RESERVED"


def test_vendor_accepts_a_reserved_order(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.post(f"{_order_path(order.id)}/accept", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACCEPTED"


def test_accepting_twice_is_an_invalid_transition(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    client.post(f"{_order_path(order.id)}/accept", headers=headers)

    response = client.post(f"{_order_path(order.id)}/accept", headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"


def test_a_customer_cannot_accept_an_order(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(f"{_order_path(order.id)}/accept", headers=headers)

    assert response.status_code == 403


def test_rejecting_requires_a_reason(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.post(f"{_order_path(order.id)}/reject", headers=headers, json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_rejecting_records_the_reason_and_takes_no_money(
    client: TestClient, db_session: Session
) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.post(
        f"{_order_path(order.id)}/reject", headers=headers, json={"reason": "Out of toner"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REJECTED"
    assert response.json()["status_reason"] == "Out of toner"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"


def test_vendor_can_start_and_mark_ready(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    client.post(f"{_order_path(order.id)}/accept", headers=headers)

    started = client.post(f"{_order_path(order.id)}/start", headers=headers)
    ready = client.post(f"{_order_path(order.id)}/ready", headers=headers)

    assert started.status_code == 200
    assert started.json()["status"] == "PRINTING"
    assert ready.status_code == 200
    assert ready.json()["status"] == "READY"


def test_collecting_with_the_right_code_completes_the_order(
    client: TestClient, db_session: Session
) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    client.post(f"{_order_path(order.id)}/accept", headers=headers)
    client.post(f"{_order_path(order.id)}/start", headers=headers)
    client.post(f"{_order_path(order.id)}/ready", headers=headers)

    response = client.post(
        f"{_order_path(order.id)}/collect", headers=headers, json={"code": order.pickup_code}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COLLECTED"


def test_collecting_with_the_wrong_code_is_rejected(
    client: TestClient, db_session: Session
) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    client.post(f"{_order_path(order.id)}/accept", headers=headers)
    client.post(f"{_order_path(order.id)}/start", headers=headers)
    client.post(f"{_order_path(order.id)}/ready", headers=headers)

    response = client.post(
        f"{_order_path(order.id)}/collect", headers=headers, json={"code": "000000"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PICKUP_CODE_INVALID"


def test_the_sixth_pickup_attempt_is_rate_limited(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    client.post(f"{_order_path(order.id)}/accept", headers=headers)
    client.post(f"{_order_path(order.id)}/start", headers=headers)
    client.post(f"{_order_path(order.id)}/ready", headers=headers)

    for _ in range(5):
        response = client.post(
            f"{_order_path(order.id)}/collect", headers=headers, json={"code": "000000"}
        )
        assert response.status_code == 400, response.text

    sixth = client.post(
        f"{_order_path(order.id)}/collect", headers=headers, json={"code": "000000"}
    )

    assert sixth.status_code == 429
    assert sixth.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in sixth.headers


def test_cancelling_an_accepted_order_requires_a_reason(
    client: TestClient, db_session: Session
) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    client.post(f"{_order_path(order.id)}/accept", headers=headers)

    response = client.post(f"{_order_path(order.id)}/cancel", headers=headers, json={})

    assert response.status_code == 422


def test_cancelling_an_accepted_order_cancels_it(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    client.post(f"{_order_path(order.id)}/accept", headers=headers)

    response = client.post(
        f"{_order_path(order.id)}/cancel", headers=headers, json={"reason": "Machine broke"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"


def test_a_vendor_cannot_touch_another_shops_order(client: TestClient, db_session: Session) -> None:
    customer, _shop, other_shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=other_shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.post(f"{_order_path(order.id)}/accept", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_vendor_file_url_is_only_for_own_shops_orders(
    client: TestClient, db_session: Session
) -> None:
    customer, _shop, other_shop = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=other_shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(f"{_order_path(order.id)}/file", headers=headers)

    assert response.status_code == 404


def test_vendor_file_url_points_at_the_stored_pdf(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(f"{_order_path(order.id)}/file", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in_seconds"] == 300
    assert body["url"].startswith("memory://")
    assert body["filename"] == "fixture.pdf"


def test_customer_cannot_reach_vendor_endpoints(client: TestClient, db_session: Session) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    actions = [
        (f"{_order_path(order.id)}/accept", "post"),
        (f"{_order_path(order.id)}/reject", "post"),
        (f"{_order_path(order.id)}/start", "post"),
        (f"{_order_path(order.id)}/ready", "post"),
        (f"{_order_path(order.id)}/cancel", "post"),
        (f"{_order_path(order.id)}/collect", "post"),
    ]
    for path, method in actions:
        response = client.request(
            method.upper(), path, headers=headers, json={"reason": "x", "code": "000000"}
        )
        assert response.status_code == 403, path

    file_response = client.get(f"{_order_path(order.id)}/file", headers=headers)
    assert file_response.status_code == 403


@pytest.mark.parametrize(
    "status",
    ["RESERVED", "ACCEPTED", "PRINTING", "READY"],
)
def test_queue_contains_every_active_status(
    client: TestClient, db_session: Session, status: str
) -> None:
    customer, shop, _ = _seed(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, VENDOR_EMAIL)
    if status != "RESERVED":
        client.post(f"{_order_path(order.id)}/accept", headers=headers)
    if status in {"PRINTING", "READY"}:
        client.post(f"{_order_path(order.id)}/start", headers=headers)
    if status == "READY":
        client.post(f"{_order_path(order.id)}/ready", headers=headers)

    response = client.get(QUEUE, headers=headers)

    assert response.status_code == 200
    assert [item["status"] for item in response.json()["items"]] == [status]


def test_the_queue_tells_the_board_when_orders_will_be_auto_rejected(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    headers = login_headers(client, VENDOR_EMAIL)

    response = client.get(QUEUE, headers=headers)

    assert response.status_code == 200
    assert response.json()["accept_timeout_minutes"] == 15
