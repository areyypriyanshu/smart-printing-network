import uuid

import pytest
from app.models import Order, OrderEvent
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_shop,
    create_upload_row,
    create_user,
    login_headers,
)

ORDERS = "/api/v1/orders"
BASE_PAISE = 200
PAGES = 5
COPIES = 2


def _seed(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop, base_paise=BASE_PAISE)
    upload = create_upload_row(session, customer=customer, page_count=PAGES)
    return customer.id, shop.id, upload.id


def _payload(upload_id: uuid.UUID, shop_id: uuid.UUID, **overrides: object) -> dict:
    body: dict[str, object] = {
        "upload_id": str(upload_id),
        "shop_id": str(shop_id),
        "paper_size": "A4",
        "color": False,
        "duplex": False,
        "copies": COPIES,
    }
    body.update(overrides)
    return body


def test_create_order_returns_the_order_with_a_price(
    client: TestClient, db_session: Session
) -> None:
    _customer_id, shop_id, upload_id = _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["order"]["status"] == "PENDING_PAYMENT"
    assert body["order"]["price_paise"] == PAGES * COPIES * BASE_PAISE
    assert body["order"]["page_count"] == PAGES
    assert body["order"]["pickup_code"] is None
    assert body["order"]["order_no"] > 0
    assert body["payment"]["provider"] == "fake"
    assert body["payment"]["amount_paise"] == PAGES * COPIES * BASE_PAISE
    assert body["payment"]["currency"] == "INR"
    assert body["payment"]["provider_order_id"].startswith("fake_order_")


def test_create_order_requires_an_idempotency_key(client: TestClient, db_session: Session) -> None:
    _customer_id, shop_id, upload_id = _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.post(ORDERS, headers=headers, json=_payload(upload_id, shop_id))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_duplicate_idempotency_key_creates_one_order(
    client: TestClient, db_session: Session
) -> None:
    customer_id, shop_id, upload_id = _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    first = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id),
    )
    second = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["order"]["id"] == second.json()["order"]["id"]
    orders = list(db_session.scalars(select(Order).where(Order.customer_id == customer_id)))
    assert len(orders) == 1


def test_expected_price_mismatch_returns_price_changed(
    client: TestClient, db_session: Session
) -> None:
    _customer_id, shop_id, upload_id = _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id, expected_price_paise=1),
    )

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "PRICE_CHANGED"
    assert body["details"]["current_price_paise"] == PAGES * COPIES * BASE_PAISE


def test_order_for_another_customers_upload_returns_404(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="owner@example.com")
    create_user(db_session, email="snooper@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop, base_paise=BASE_PAISE)
    upload = create_upload_row(db_session, customer=owner, page_count=PAGES)
    headers = login_headers(client, "snooper@example.com")

    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload.id, shop.id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_order_creation_is_forbidden_for_vendors(client: TestClient, db_session: Session) -> None:
    _customer_id, shop_id, upload_id = _seed(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id),
    )

    assert response.status_code == 403


def test_order_creation_requires_authentication(client: TestClient, db_session: Session) -> None:
    _customer_id, shop_id, upload_id = _seed(db_session)

    response = client.post(
        ORDERS,
        headers={"Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id),
    )

    assert response.status_code == 401


def test_list_orders_returns_the_customers_orders(client: TestClient, db_session: Session) -> None:
    _customer_id, shop_id, upload_id = _seed(db_session)
    headers = login_headers(client, "customer@example.com")
    client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id),
    )

    response = client.get(ORDERS, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["price_paise"] == PAGES * COPIES * BASE_PAISE
    assert body["next_cursor"] is None


def test_order_detail_is_hidden_from_other_customers(
    client: TestClient, db_session: Session
) -> None:
    _customer_id, shop_id, upload_id = _seed(db_session)
    create_user(db_session, email="snooper@example.com")
    headers = login_headers(client, "customer@example.com")
    created = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id),
    )
    snooper_headers = login_headers(client, "snooper@example.com")

    response = client.get(f"{ORDERS}/{created.json()['order']['id']}", headers=snooper_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_order_detail_contains_the_timeline(client: TestClient, db_session: Session) -> None:
    _customer_id, shop_id, upload_id = _seed(db_session)
    headers = login_headers(client, "customer@example.com")
    created = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id),
    )

    response = client.get(f"{ORDERS}/{created.json()['order']['id']}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["order"]["status"] == "PENDING_PAYMENT"
    assert [event["to_status"] for event in body["events"]] == ["PENDING_PAYMENT"]


def test_order_creation_rejects_invalid_copies(client: TestClient, db_session: Session) -> None:
    _customer_id, shop_id, upload_id = _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json=_payload(upload_id, shop_id, copies=0),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_database_rejects_an_order_whose_price_breaks_the_formula(
    db_session: Session,
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    upload = create_upload_row(db_session, customer=customer)

    db_session.add(
        Order(
            customer_id=customer.id,
            shop_id=shop.id,
            upload_id=upload.id,
            status="PENDING_PAYMENT",
            paper_size="A4",
            color=False,
            duplex=False,
            copies=2,
            page_count=5,
            rate_paise=200,
            min_order_paise=0,
            price_paise=999,
            idempotency_key="key-1",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_rejects_a_paid_order_without_a_pickup_code(db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    upload = create_upload_row(db_session, customer=customer)

    db_session.add(
        Order(
            customer_id=customer.id,
            shop_id=shop.id,
            upload_id=upload.id,
            status="PAID",
            paper_size="A4",
            color=False,
            duplex=False,
            copies=2,
            page_count=5,
            rate_paise=200,
            min_order_paise=0,
            price_paise=2000,
            idempotency_key="key-1",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_order_events_are_written_only_by_the_service(db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    upload = create_upload_row(db_session, customer=customer)
    order = Order(
        customer_id=customer.id,
        shop_id=shop.id,
        upload_id=upload.id,
        status="PENDING_PAYMENT",
        paper_size="A4",
        color=False,
        duplex=False,
        copies=1,
        page_count=1,
        rate_paise=200,
        min_order_paise=0,
        price_paise=200,
        idempotency_key="key-1",
    )
    db_session.add(order)
    db_session.commit()

    assert list(db_session.scalars(select(OrderEvent))) == []


def test_a_cursor_above_the_bigint_range_is_refused(
    client: TestClient, db_session: Session
) -> None:
    """A cursor the database cannot hold is refused at the edge.

    The cursor is an order number, and the column is a bigint. A cursor
    above the range of a bigint used to be handed to the database, which
    answered with a server error, so any client could produce one.
    """
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")

    response = client.get(f"{ORDERS}?cursor=8137899453232152163230154752", headers=headers)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_cursor_inside_the_bigint_range_is_accepted(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")

    response = client.get(f"{ORDERS}?cursor=9223372036854775807", headers=headers)

    assert response.status_code == 200, response.text
