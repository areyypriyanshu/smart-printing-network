"""The shops around a point.

The customer wants a shop near them, not a list ordered by when it was
created. The distance is measured in metres, because that is what
"nearby" means.
"""

from fastapi.testclient import TestClient
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
