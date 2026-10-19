import uuid
from pathlib import Path

from app.models import ShopRate
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_shop,
    create_upload_row,
    create_user,
    login_headers,
)
from tests.fixtures.pdf_files import make_pdf

QUOTES = "/api/v1/quotes"
UPLOADS = "/api/v1/uploads"


def _upload(client: TestClient, headers: dict[str, str], tmp_path: Path) -> dict:
    with make_pdf(tmp_path / "valid.pdf", pages=5).open("rb") as handle:
        response = client.post(
            UPLOADS, headers=headers, files={"file": ("valid.pdf", handle, "application/pdf")}
        )
    assert response.status_code == 201, response.text
    return response.json()


def test_quote_computes_price_from_rate_pages_and_copies(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop, base_paise=200)
    headers = login_headers(client, "customer@example.com")
    upload = _upload(client, headers, tmp_path)

    response = client.post(
        QUOTES,
        headers=headers,
        json={
            "upload_id": upload["id"],
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 2,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 5
    assert body["rate_paise"] == 200
    assert body["price_paise"] == 5 * 2 * 200
    assert body["copies"] == 2
    assert body["min_order_paise"] == shop.min_order_paise


def test_quote_applies_minimum_order(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor, min_order_paise=5000)
    create_full_rate_table(db_session, shop, base_paise=100)
    headers = login_headers(client, "customer@example.com")
    upload = _upload(client, headers, tmp_path)

    response = client.post(
        QUOTES,
        headers=headers,
        json={
            "upload_id": upload["id"],
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["price_paise"] == 5000


def test_quote_without_matching_rate_returns_rate_not_set(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    db_session.add(
        ShopRate(shop_id=shop.id, paper_size="A4", color=False, duplex=False, rate_paise=200)
    )
    db_session.commit()
    headers = login_headers(client, "customer@example.com")
    upload = _upload(client, headers, tmp_path)

    response = client.post(
        QUOTES,
        headers=headers,
        json={
            "upload_id": upload["id"],
            "shop_id": str(shop.id),
            "paper_size": "A3",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RATE_NOT_SET"


def test_quote_for_unverified_shop_returns_shop_unavailable(
    client: TestClient, db_session: Session
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor, is_verified=False)
    create_full_rate_table(db_session, shop)
    upload = create_upload_row(db_session, customer=customer)
    headers = login_headers(client, "customer@example.com")

    response = client.post(
        QUOTES,
        headers=headers,
        json={
            "upload_id": str(upload.id),
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SHOP_UNAVAILABLE"


def test_quote_for_shop_not_accepting_returns_shop_unavailable(
    client: TestClient, db_session: Session
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor, accepting_orders=False)
    create_full_rate_table(db_session, shop)
    upload = create_upload_row(db_session, customer=customer)
    headers = login_headers(client, "customer@example.com")

    response = client.post(
        QUOTES,
        headers=headers,
        json={
            "upload_id": str(upload.id),
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SHOP_UNAVAILABLE"


def test_quote_for_missing_shop_returns_404(client: TestClient, db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    upload = create_upload_row(db_session, customer=customer)
    headers = login_headers(client, "customer@example.com")

    response = client.post(
        QUOTES,
        headers=headers,
        json={
            "upload_id": str(upload.id),
            "shop_id": str(uuid.uuid4()),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_quote_for_another_customers_upload_returns_404(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="owner@example.com")
    create_user(db_session, email="snooper@example.com")
    upload = create_upload_row(db_session, customer=owner)
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    headers = login_headers(client, "snooper@example.com")

    response = client.post(
        QUOTES,
        headers=headers,
        json={
            "upload_id": str(upload.id),
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_quote_forbidden_for_vendors(client: TestClient, db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    upload = create_upload_row(db_session, customer=customer)
    headers = login_headers(client, "vendor@example.com")

    response = client.post(
        QUOTES,
        headers=headers,
        json={
            "upload_id": str(upload.id),
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
    )

    assert response.status_code == 403


def test_quote_rejects_invalid_copies(client: TestClient, db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    upload = create_upload_row(db_session, customer=customer)
    headers = login_headers(client, "customer@example.com")

    for copies in (0, 101):
        response = client.post(
            QUOTES,
            headers=headers,
            json={
                "upload_id": str(upload.id),
                "shop_id": str(shop.id),
                "paper_size": "A4",
                "color": False,
                "duplex": False,
                "copies": copies,
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
