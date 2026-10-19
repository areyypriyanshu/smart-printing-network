import uuid

from app.cli import verify_shop
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import create_full_rate_table, create_shop, create_user, login_headers

SHOPS = "/api/v1/shops"


def test_shops_list_hides_unverified_shops_until_verified(
    client: TestClient, db_session: Session
) -> None:
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor, is_verified=False, name="Hidden Prints")
    create_full_rate_table(db_session, shop)
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")

    before = client.get(SHOPS, headers=headers)
    assert before.status_code == 200
    assert before.json()["items"] == []

    assert verify_shop(db_session, "vendor@example.com") == 0

    after = client.get(SHOPS, headers=headers)
    assert after.status_code == 200
    items = after.json()["items"]
    assert [item["name"] for item in items] == ["Hidden Prints"]
    assert len(items[0]["rates"]) == 8


def test_shops_list_excludes_non_accepting_shops(client: TestClient, db_session: Session) -> None:
    vendor = create_user(db_session, email="closed@example.com", role="vendor")
    create_shop(db_session, owner=vendor, is_verified=True, accepting_orders=False)
    create_user(db_session, email="customer2@example.com")
    headers = login_headers(client, "customer2@example.com")

    response = client.get(SHOPS, headers=headers)

    assert response.json()["items"] == []


def test_shops_list_requires_customer_role(client: TestClient, db_session: Session) -> None:
    vendor = create_user(db_session, email="v@example.com", role="vendor")
    create_shop(db_session, owner=vendor)

    anonymous = client.get(SHOPS)
    assert anonymous.status_code == 401

    response = client.get(SHOPS, headers=login_headers(client, "v@example.com"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_shop_detail_returns_coordinates_in_correct_order(
    client: TestClient, db_session: Session
) -> None:
    vendor = create_user(db_session, email="coords@example.com", role="vendor")
    shop = create_shop(
        db_session,
        owner=vendor,
        latitude=22.5726,
        longitude=88.3639,
        is_verified=True,
    )
    create_full_rate_table(db_session, shop)
    create_user(db_session, email="viewer@example.com")
    headers = login_headers(client, "viewer@example.com")

    response = client.get(f"{SHOPS}/{shop.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert abs(body["latitude"] - 22.5726) < 1e-9
    assert abs(body["longitude"] - 88.3639) < 1e-9


def test_shop_detail_hides_unverified_and_unknown_shops(
    client: TestClient, db_session: Session
) -> None:
    vendor = create_user(db_session, email="unverified@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor, is_verified=False)
    create_user(db_session, email="browser@example.com")
    headers = login_headers(client, "browser@example.com")

    hidden = client.get(f"{SHOPS}/{shop.id}", headers=headers)
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "NOT_FOUND"

    unknown = client.get(f"{SHOPS}/{uuid.uuid4()}", headers=headers)
    assert unknown.status_code == 404


def test_shops_list_paginates_with_cursor(client: TestClient, db_session: Session) -> None:
    for index in range(3):
        vendor = create_user(db_session, email=f"page-{index}@example.com", role="vendor")
        shop = create_shop(db_session, owner=vendor, name=f"Shop {index}", is_verified=True)
        create_full_rate_table(db_session, shop)
    create_user(db_session, email="pager@example.com")
    headers = login_headers(client, "pager@example.com")

    first = client.get(SHOPS, params={"limit": 2}, headers=headers)
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    cursor = first.json()["next_cursor"]
    assert cursor

    second = client.get(SHOPS, params={"limit": 2, "cursor": cursor}, headers=headers)
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None


def test_shops_list_rejects_invalid_cursor(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="badcursor@example.com")
    headers = login_headers(client, "badcursor@example.com")

    response = client.get(SHOPS, params={"cursor": "not-base64!!"}, headers=headers)

    assert response.status_code == 422
