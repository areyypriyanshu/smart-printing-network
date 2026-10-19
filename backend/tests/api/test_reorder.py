"""Printing the same job again.

The file is copied rather than shared, so the two orders never depend on
each other, and the guarantee that a file is deleted after the retention
window holds for both.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.gateways.storage import MemoryStorage
from app.models import Order, Upload
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_paid_order,
    create_shop,
    create_user,
    login_headers,
)

ORDERS = "/api/v1/orders"
CUSTOMER_EMAIL = "customer@example.com"
OTHER_EMAIL = "other@example.com"


def _seed(session: Session) -> tuple[object, object]:
    customer = create_user(session, email=CUSTOMER_EMAIL)
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    return customer, shop


def _store_the_file(client: TestClient, session: Session, order: Order) -> Upload:
    """Put the file in storage, the way an upload does.

    The factory builds the rows without touching storage, so a test that
    copies a file has to put it there first.
    """
    upload = session.get(Upload, order.upload_id)
    assert upload is not None
    storage: MemoryStorage = client.app.state.storage
    storage.objects[upload.file_key] = b"%PDF-1.4\n% a stored file\n"
    return upload


def test_reordering_copies_the_file(client: TestClient, db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    _store_the_file(client, db_session, order)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(f"{ORDERS}/{order.id}/reorder", headers=headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["paper_size"] == order.paper_size
    assert body["color"] == order.color
    assert body["duplex"] == order.duplex
    assert body["copies"] == order.copies
    assert body["shop_id"] == str(shop.id)

    storage: MemoryStorage = client.app.state.storage
    assert len(storage.objects) == 2
    copy = db_session.get(Upload, uuid.UUID(body["upload_id"]))
    assert copy is not None
    original = db_session.get(Upload, order.upload_id)
    assert original is not None
    assert copy.file_key != original.file_key
    assert copy.page_count == order.page_count
    assert copy.sha256 == original.sha256


def test_the_copy_has_its_own_retention_window(client: TestClient, db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    _store_the_file(client, db_session, order)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(f"{ORDERS}/{order.id}/reorder", headers=headers)

    assert response.status_code == 201, response.text
    copy = db_session.get(Upload, uuid.UUID(response.json()["upload_id"]))
    assert copy is not None
    assert copy.delete_after is not None
    expected = datetime.now(UTC) + timedelta(hours=24)
    assert abs((copy.delete_after - expected).total_seconds()) < 60


def test_reordering_after_the_file_is_deleted_says_so(
    client: TestClient, db_session: Session
) -> None:
    """The file is gone. The honest answer is to upload it again."""
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    upload = db_session.get(Upload, order.upload_id)
    assert upload is not None
    upload.file_deleted_at = datetime.now(UTC)
    db_session.commit()
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.post(f"{ORDERS}/{order.id}/reorder", headers=headers)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "FILE_UNAVAILABLE"
    assert "upload it" in body["error"]["message"].lower()


def test_the_order_detail_says_whether_the_file_is_still_there(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, CUSTOMER_EMAIL)

    response = client.get(f"{ORDERS}/{order.id}", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["file_available"] is True

    upload = db_session.get(Upload, order.upload_id)
    assert upload is not None
    upload.file_deleted_at = datetime.now(UTC)
    db_session.commit()

    response = client.get(f"{ORDERS}/{order.id}", headers=headers)
    assert response.json()["file_available"] is False


def test_a_customer_cannot_reorder_somebody_elses_order(
    client: TestClient, db_session: Session
) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    create_user(db_session, email=OTHER_EMAIL)
    headers = login_headers(client, OTHER_EMAIL)

    response = client.post(f"{ORDERS}/{order.id}/reorder", headers=headers)

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_reordering_needs_authentication(client: TestClient, db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)

    response = client.post(f"{ORDERS}/{order.id}/reorder")

    assert response.status_code == 401, response.text


def test_a_vendor_cannot_reorder_a_customers_job(client: TestClient, db_session: Session) -> None:
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    headers = login_headers(client, "vendor@example.com")

    response = client.post(f"{ORDERS}/{order.id}/reorder", headers=headers)

    assert response.status_code == 403, response.text


def test_reordering_leaves_the_original_order_alone(
    client: TestClient, db_session: Session
) -> None:
    """A new order is a new order. The old one is not touched."""
    customer, shop = _seed(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    _store_the_file(client, db_session, order)
    headers = login_headers(client, CUSTOMER_EMAIL)

    client.post(f"{ORDERS}/{order.id}/reorder", headers=headers)

    stored = db_session.get(Order, order.id)
    assert stored is not None
    assert stored.status == "PAID"
    uploads = list(db_session.scalars(select(Upload)))
    assert len(uploads) == 2
