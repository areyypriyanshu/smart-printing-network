import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_reserved_order,
    create_shop,
    create_user,
    login_headers,
)


def _shop(session: Session, *, verified: bool = True, accepting: bool = True):
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor, is_verified=verified, accepting_orders=accepting)
    create_full_rate_table(session, shop)
    return shop


def test_customer_gets_an_aggregate_rough_estimate(client: TestClient, db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    shop = _shop(db_session)
    create_reserved_order(db_session, customer=customer, shop=shop, page_count=4, copies=1)

    response = client.get(
        f"/api/v1/shops/{shop.id}/wait-estimate",
        headers=login_headers(client, "customer@example.com"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["shop_id"] == str(shop.id)
    assert body["minimum_minutes"] == pytest.approx(1.4)
    assert body["median_minutes"] == pytest.approx(2)
    assert body["maximum_minutes"] == pytest.approx(3)
    assert body["sample_count"] == 0
    assert body["rough"] is True
    assert body["algorithm_version"] == "1"
    assert "queue_orders" not in body
    assert "queue_units" not in body
    assert "events" not in body


def test_wait_estimate_requires_authentication(client: TestClient, db_session: Session) -> None:
    shop = _shop(db_session)

    response = client.get(f"/api/v1/shops/{shop.id}/wait-estimate")

    assert response.status_code == 401


@pytest.mark.parametrize("role", ["vendor", "admin"])
def test_wait_estimate_refuses_other_roles(
    client: TestClient, db_session: Session, role: str
) -> None:
    email = f"{role}-actor@example.com"
    create_user(db_session, email=email, role=role)
    shop = _shop(db_session)

    response = client.get(
        f"/api/v1/shops/{shop.id}/wait-estimate", headers=login_headers(client, email)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_wait_estimate_conceals_unknown_and_unverified_shops(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="customer@example.com")
    hidden = _shop(db_session, verified=False)
    headers = login_headers(client, "customer@example.com")

    unknown = client.get(f"/api/v1/shops/{uuid.uuid4()}/wait-estimate", headers=headers)
    unverified = client.get(f"/api/v1/shops/{hidden.id}/wait-estimate", headers=headers)

    assert unknown.status_code == 404
    assert unverified.status_code == 404
    assert unknown.json()["error"]["code"] == "NOT_FOUND"


def test_verified_non_accepting_shop_remains_readable(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="customer@example.com")
    shop = _shop(db_session, accepting=False)

    response = client.get(
        f"/api/v1/shops/{shop.id}/wait-estimate",
        headers=login_headers(client, "customer@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["maximum_minutes"] == 0


def test_shop_lists_batch_the_estimate(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="customer@example.com")
    _shop(db_session)
    headers = login_headers(client, "customer@example.com")

    listed = client.get("/api/v1/shops", headers=headers)
    nearby = client.get(
        "/api/v1/shops/nearby",
        params={"latitude": 22.5726, "longitude": 88.3639},
        headers=headers,
    )
    searched = client.get("/api/v1/shops/search", headers=headers)

    for response in (listed, nearby, searched):
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == 1
        estimate = response.json()["items"][0]["wait_estimate"]
        assert estimate["rough"] is True
        assert estimate["sample_count"] == 0


def test_a_statistics_failure_does_not_hide_the_shop_list(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_user(db_session, email="customer@example.com")
    _shop(db_session)

    def fail_statistics(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("simulated statistics failure")

    monkeypatch.setattr("app.services.estimate_service.estimates_for_shops", fail_statistics)

    response = client.get("/api/v1/shops", headers=login_headers(client, "customer@example.com"))

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["wait_estimate"] is None
