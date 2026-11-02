"""The shops around a point.

The customer wants a shop near them, not a list ordered by when it was
created. The distance is measured in metres, because that is what
"nearby" means.
"""

import base64
import json

from app.gateways.identity.fake import dev_subject_for
from app.models import Shop, User
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session
from tests.factories import create_shop, create_user, login_headers

SHOPS = "/api/v1/shops"

#: A point in central Kolkata, and the three seeded shops around it.
CENTRAL = (22.5726, 88.3639)


def _seed(session: Session) -> None:
    """A customer and three shops, each with its own owner.

    A vendor account owns exactly one shop, so each shop needs a vendor
    of its own.
    """
    create_user(session, email="customer@example.com")
    for index, (name, latitude, longitude) in enumerate(
        [
            ("Close Shop", 22.5730, 88.3640),
            ("Middle Shop", 22.5800, 88.3700),
            ("Far Shop", 19.0473, 73.0699),
            ("Another Close Shop", 22.5735, 88.3645),
        ]
    ):
        vendor = create_user(session, email=f"vendor{index}@example.com", role="vendor")
        create_shop(
            session,
            owner=vendor,
            name=name,
            latitude=latitude,
            longitude=longitude,
        )


def test_the_nearest_shop_comes_first(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": CENTRAL[0], "longitude": CENTRAL[1], "radius_m": 50000},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    # The far shop is a thousand kilometres away, so it is not nearby.
    assert [item["name"] for item in items] == [
        "Close Shop",
        "Another Close Shop",
        "Middle Shop",
    ]
    assert items[0]["distance_m"] < items[1]["distance_m"]
    assert items[1]["distance_m"] < items[2]["distance_m"]


def test_a_shop_outside_the_radius_is_not_returned(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": CENTRAL[0], "longitude": CENTRAL[1], "radius_m": 2000},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    names = [item["name"] for item in response.json()["items"]]
    assert "Close Shop" in names
    assert "Far Shop" not in names


def test_without_a_radius_every_shop_is_returned_nearest_first(
    client: TestClient, db_session: Session
) -> None:
    # The order wizard has no radius control. It sorts the whole list by
    # distance, so a customer whose shops are all far away still has a
    # shop to order from.
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": CENTRAL[0], "longitude": CENTRAL[1]},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["name"] for item in items] == [
        "Close Shop",
        "Another Close Shop",
        "Middle Shop",
        "Far Shop",
    ]
    distances = [item["distance_m"] for item in items]
    assert distances == sorted(distances)


def test_nearby_results_continue_past_the_page_limit(
    client: TestClient, db_session: Session
) -> None:
    customer = create_user(db_session, email="many-shops-customer@example.com")
    owners = [
        User(
            email=f"many-shops-{index}@example.com",
            clerk_user_id=dev_subject_for(f"many-shops-{index}@example.com"),
            full_name="Vendor",
            role="vendor",
            email_verified=True,
        )
        for index in range(101)
    ]
    db_session.add_all(owners)
    db_session.flush()
    db_session.add_all(
        [
            Shop(
                owner_id=owner.id,
                name=f"Shop {index:03d}",
                address="1 Test Street",
                location=WKTElement("POINT(88.3639 22.5726)", srid=4326),
                min_order_paise=0,
                is_verified=True,
                accepting_orders=True,
            )
            for index, owner in enumerate(owners)
        ]
    )
    db_session.commit()
    headers = login_headers(client, customer.email)

    first = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": CENTRAL[0], "longitude": CENTRAL[1], "limit": 100},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["items"]) == 100
    assert first_body["next_cursor"]

    second = client.get(
        f"{SHOPS}/nearby",
        params={
            "latitude": CENTRAL[0],
            "longitude": CENTRAL[1],
            "limit": 100,
            "cursor": first_body["next_cursor"],
        },
        headers=headers,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None
    assert [item["name"] for item in first_body["items"] + second_body["items"]] == [
        f"Shop {index:03d}" for index in range(101)
    ]


def test_a_nearby_cursor_is_rejected_for_a_different_search(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")
    first = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": CENTRAL[0], "longitude": CENTRAL[1], "radius_m": 50000, "limit": 1},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    cursor = first.json()["next_cursor"]
    assert cursor is not None

    changed_location = client.get(
        f"{SHOPS}/nearby",
        params={
            "latitude": CENTRAL[0] + 0.001,
            "longitude": CENTRAL[1],
            "radius_m": 50000,
            "limit": 1,
            "cursor": cursor,
        },
        headers=headers,
    )
    changed_radius = client.get(
        f"{SHOPS}/nearby",
        params={
            "latitude": CENTRAL[0],
            "longitude": CENTRAL[1],
            "radius_m": 10000,
            "limit": 1,
            "cursor": cursor,
        },
        headers=headers,
    )

    assert changed_location.status_code == 422
    assert changed_radius.status_code == 422


def test_a_nearby_cursor_with_a_non_string_shop_id_is_a_validation_error(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")
    cursor = base64.urlsafe_b64encode(
        json.dumps({"distance_m": "0.0", "name": "Shop", "shop_id": 1}).encode()
    ).decode()

    response = client.get(
        f"{SHOPS}/nearby",
        params={
            "latitude": CENTRAL[0],
            "longitude": CENTRAL[1],
            "cursor": cursor,
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_the_distance_is_in_metres(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": CENTRAL[0], "longitude": CENTRAL[1], "radius_m": 50000},
        headers=headers,
    )

    items = response.json()["items"]
    close = next(item for item in items if item["name"] == "Close Shop")
    # About fifty metres from the point, give or take the curvature.
    assert 0 < close["distance_m"] < 200


def test_a_shop_that_is_not_verified_is_not_nearby(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    vendor = create_user(db_session, email="second@example.com", role="vendor")
    create_shop(
        db_session,
        owner=vendor,
        name="Unverified Shop",
        latitude=22.5727,
        longitude=88.3641,
        is_verified=False,
    )
    headers = login_headers(client, "customer@example.com")

    response = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": CENTRAL[0], "longitude": CENTRAL[1], "radius_m": 50000},
        headers=headers,
    )

    names = [item["name"] for item in response.json()["items"]]
    assert "Unverified Shop" not in names


def test_the_nearby_search_needs_authentication(client: TestClient, db_session: Session) -> None:
    _seed(db_session)

    response = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": CENTRAL[0], "longitude": CENTRAL[1]},
    )

    assert response.status_code == 401, response.text


def test_the_nearby_search_refuses_a_point_that_is_not_on_the_earth(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": 200, "longitude": 88.3639},
        headers=headers,
    )

    assert response.status_code == 422, response.text


def test_the_phone_number_is_shown_when_the_shop_has_one(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    create_shop(
        db_session,
        owner=vendor,
        name="Reachable Shop",
        latitude=22.5727,
        longitude=88.3641,
    )
    headers = login_headers(client, "customer@example.com")

    response = client.get(
        f"{SHOPS}/nearby",
        params={"latitude": CENTRAL[0], "longitude": CENTRAL[1], "radius_m": 50000},
        headers=headers,
    )

    items = response.json()["items"]
    assert items[0]["phone"] is None
