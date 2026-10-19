import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import create_shop, create_user, login_headers

VENDOR_SHOP = "/api/v1/vendor/shop"
VENDOR_RATES = "/api/v1/vendor/rates"


def create_vendor_with_shop(session: Session, email: str = "vendor@example.com") -> None:
    vendor = create_user(session, email=email, role="vendor")
    create_shop(
        session,
        owner=vendor,
        name="Vendor Prints",
        min_order_paise=1000,
        is_verified=False,
    )


def test_get_own_shop(client: TestClient, db_session: Session) -> None:
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.get(VENDOR_SHOP, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Vendor Prints"
    assert body["min_order_paise"] == 1000
    assert body["is_verified"] is False


def test_vendor_never_sees_another_vendors_shop(client: TestClient, db_session: Session) -> None:
    other = create_user(db_session, email="other@example.com", role="vendor")
    other_shop = create_shop(db_session, owner=other, name="Other Prints")
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.get(VENDOR_SHOP, headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] != str(other_shop.id)
    assert response.json()["name"] == "Vendor Prints"


def test_vendor_without_shop_gets_not_found(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="shopless@example.com", role="vendor")
    headers = login_headers(client, "shopless@example.com")

    response = client.get(VENDOR_SHOP, headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_customer_cannot_access_vendor_endpoints(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")

    for path in (VENDOR_SHOP, VENDOR_RATES):
        response = client.get(path, headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    assert client.patch(VENDOR_SHOP, json={"name": "X"}, headers=headers).status_code == 403
    assert client.put(VENDOR_RATES, json={"rates": []}, headers=headers).status_code == 403


def test_patch_shop_updates_fields(client: TestClient, db_session: Session) -> None:
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.patch(
        VENDOR_SHOP,
        json={"name": "Renamed Prints", "min_order_paise": 2500, "accepting_orders": False},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed Prints"
    assert body["min_order_paise"] == 2500
    assert body["accepting_orders"] is False


def test_patch_shop_rejects_negative_min_order(client: TestClient, db_session: Session) -> None:
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.patch(VENDOR_SHOP, json={"min_order_paise": -1}, headers=headers)

    assert response.status_code == 422


def test_put_rates_replaces_full_set(client: TestClient, db_session: Session) -> None:
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")
    rates = [
        {"paper_size": "A4", "color": False, "duplex": False, "rate_paise": 200},
        {"paper_size": "A3", "color": True, "duplex": True, "rate_paise": 1500},
    ]

    saved = client.put(VENDOR_RATES, json={"rates": rates}, headers=headers)
    assert saved.status_code == 200
    assert len(saved.json()) == 2

    fetched = client.get(VENDOR_RATES, headers=headers)
    assert fetched.status_code == 200
    assert {
        (r["paper_size"], r["color"], r["duplex"], r["rate_paise"]) for r in fetched.json()
    } == {
        ("A4", False, False, 200),
        ("A3", True, True, 1500),
    }

    replaced = client.put(
        VENDOR_RATES,
        json={"rates": [{"paper_size": "A4", "color": False, "duplex": False, "rate_paise": 250}]},
        headers=headers,
    )
    assert replaced.status_code == 200
    assert len(replaced.json()) == 1
    assert replaced.json()[0]["rate_paise"] == 250


def test_put_rates_empty_clears_all(client: TestClient, db_session: Session) -> None:
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")
    client.put(
        VENDOR_RATES,
        json={"rates": [{"paper_size": "A4", "color": False, "duplex": False, "rate_paise": 200}]},
        headers=headers,
    )

    cleared = client.put(VENDOR_RATES, json={"rates": []}, headers=headers)

    assert cleared.status_code == 200
    assert cleared.json() == []
    assert client.get(VENDOR_RATES, headers=headers).json() == []


@pytest.mark.parametrize("rate_paise", [0, -5, 2.5])
def test_put_rates_rejects_invalid_amounts(
    client: TestClient, db_session: Session, rate_paise: float
) -> None:
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.put(
        VENDOR_RATES,
        json={
            "rates": [
                {"paper_size": "A4", "color": False, "duplex": False, "rate_paise": rate_paise}
            ]
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_put_rates_rejects_duplicate_combinations(client: TestClient, db_session: Session) -> None:
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.put(
        VENDOR_RATES,
        json={
            "rates": [
                {"paper_size": "A4", "color": False, "duplex": False, "rate_paise": 200},
                {"paper_size": "A4", "color": False, "duplex": False, "rate_paise": 300},
            ]
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_put_rates_rejects_unknown_paper_size(client: TestClient, db_session: Session) -> None:
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.put(
        VENDOR_RATES,
        json={"rates": [{"paper_size": "A5", "color": False, "duplex": False, "rate_paise": 200}]},
        headers=headers,
    )

    assert response.status_code == 422


def test_put_rates_rejects_more_than_eight_rows(client: TestClient, db_session: Session) -> None:
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")
    rates = [
        {"paper_size": size, "color": color, "duplex": duplex, "rate_paise": 200}
        for size in ("A4", "A3")
        for color in (False, True)
        for duplex in (False, True)
    ] * 2

    response = client.put(VENDOR_RATES, json={"rates": rates}, headers=headers)

    assert response.status_code == 422
