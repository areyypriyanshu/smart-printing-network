import pytest
from app.models import Shop, ShopRate
from fastapi.testclient import TestClient
from sqlalchemy import select
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


@pytest.mark.parametrize("rate_paise", [0, -5, 2.5, 50_001])
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


def test_put_rates_rejects_a_page_that_costs_more_than_the_ceiling(
    client: TestClient, db_session: Session
) -> None:
    """The price of an order is pages x copies x rate, and the column
    that holds it is a 32 bit integer. A rate above the ceiling would
    let a shop price an order the database cannot hold, and the
    failure would land on the customer who tried to order.
    """
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.put(
        VENDOR_RATES,
        json={
            "rates": [
                {
                    "paper_size": "A4",
                    "color": False,
                    "duplex": False,
                    "rate_paise": 2_000_000_000,
                }
            ]
        },
        headers=headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_rate_stored_before_the_ceiling_can_still_be_read(
    client: TestClient, db_session: Session
) -> None:
    """A rate is read back for the shop's table and for the customer
    comparing prices. Refusing to read one would turn one shop's
    strange rate into a page that does not load for anybody.
    """
    create_vendor_with_shop(db_session)
    shop = db_session.scalar(select(Shop).where(Shop.name == "Vendor Prints"))
    assert shop is not None
    db_session.add(
        ShopRate(
            shop_id=shop.id, paper_size="A4", color=False, duplex=False, rate_paise=2_000_000_000
        )
    )
    db_session.commit()
    headers = login_headers(client, "vendor@example.com")

    response = client.get(VENDOR_RATES, headers=headers)

    assert response.status_code == 200, response.text
    assert any(item["rate_paise"] == 2_000_000_000 for item in response.json())


def test_a_minimum_order_above_the_ceiling_is_refused(
    client: TestClient, db_session: Session
) -> None:
    """It is held in the same kind of column as the price of a page,
    so it has the same kind of ceiling. Refusing it at the door is a
    422; letting it through is a failure later."""
    create_vendor_with_shop(db_session)
    headers = login_headers(client, "vendor@example.com")

    response = client.patch(
        VENDOR_SHOP,
        json={"min_order_paise": 3_000_000_000},
        headers=headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


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
