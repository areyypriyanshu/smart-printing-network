import uuid

from app.models import Payment, Upload
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_paid_order,
    create_shop,
    create_upload_row,
    create_user,
    login_headers,
)

ORDERS = "/api/v1/orders"
CUSTOMER_EMAIL = "customer@example.com"
OTHER_CUSTOMER_EMAIL = "other@example.com"


def _seed(session: Session) -> tuple[object, object]:
    customer = create_user(session, email=CUSTOMER_EMAIL)
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    return customer, shop


def test_a_customer_can_cancel_an_order_that_is_still_waiting_for_payment(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(f"{ORDERS}/{order.id}/cancel", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"


def test_cancelling_a_paid_order_queues_a_refund(client: TestClient, db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(f"{ORDERS}/{order.id}/cancel", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"
    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "REFUND_PENDING"


def test_a_customer_cannot_cancel_after_the_shop_accepted(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    vendor_headers = login_headers(client, "vendor@example.com")
    client.post(f"/api/v1/vendor/orders/{order.id}/accept", headers=vendor_headers)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(f"{ORDERS}/{order.id}/cancel", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_cancelling_another_customers_order_is_not_found(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    create_user(db_session, email=OTHER_CUSTOMER_EMAIL)
    headers = login_headers(client, OTHER_CUSTOMER_EMAIL)

    response = client.post(f"{ORDERS}/{order.id}/cancel", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_customer_gets_a_short_lived_link_to_their_own_file(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.get(f"{ORDERS}/{order.id}/file", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in_seconds"] == 300
    assert body["url"].startswith("memory://")
    assert body["filename"] == "fixture.pdf"


def test_a_customer_cannot_get_another_customers_file(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    create_user(db_session, email=OTHER_CUSTOMER_EMAIL)
    headers = login_headers(client, OTHER_CUSTOMER_EMAIL)

    response = client.get(f"{ORDERS}/{order.id}/file", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_file_that_was_purged_is_not_found(client: TestClient, db_session: Session) -> None:
    from datetime import UTC, datetime

    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    upload = db_session.get(Upload, order.upload_id)
    assert upload is not None
    upload.file_deleted_at = datetime.now(UTC)
    db_session.commit()
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.get(f"{ORDERS}/{order.id}/file", headers=headers)

    assert response.status_code == 404


def test_the_file_endpoint_requires_authentication(client: TestClient, db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)

    response = client.get(f"{ORDERS}/{order.id}/file")

    assert response.status_code == 401


def test_the_file_endpoint_is_forbidden_for_a_vendor(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, "vendor@example.com")

    response = client.get(f"{ORDERS}/{order.id}/file", headers=headers)

    assert response.status_code == 403


def test_the_customer_order_detail_shows_the_pickup_code(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.get(f"{ORDERS}/{order.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["order"]["pickup_code"] == order.pickup_code


def test_an_unpaid_order_has_no_pickup_code(client: TestClient, db_session: Session) -> None:
    from app.gateways.payments import FakeGateway
    from app.schemas.order import OrderCreateRequest
    from app.services import order_service

    customer, shop = _seed(db_session)
    upload = create_upload_row(db_session, customer=customer, page_count=1)
    order, _payment = order_service.create_order(
        db_session,
        customer_id=customer.id,
        request=OrderCreateRequest(
            upload_id=upload.id,
            shop_id=shop.id,
            paper_size="A4",
            color=False,
            duplex=False,
            copies=1,
        ),
        idempotency_key=uuid.uuid4().hex,
        gateway=FakeGateway(),
    )
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.get(f"{ORDERS}/{order.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["order"]["pickup_code"] is None
