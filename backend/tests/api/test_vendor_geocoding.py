"""Where a new shop is placed.

A shop owner says where their shop is. They can type the coordinates,
or they can type the address and let the map provider find it. The
coordinates they type come first, because a shop owner knows where
their own shop is better than a map does.
"""

from app.gateways.geocoding import GeocodeResult, MemoryGeocoder
from app.gateways.identity.clerk_admin import ClerkUser
from app.models import Shop, User
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.factories import identity_headers

ONBOARDING = "/api/v1/auth/onboarding"
SUBJECT = "user_shop_owner"


def _tell_the_provider_about(client: TestClient, subject: str) -> None:
    reader = client.app.state.identity_reader
    reader.people[subject] = ClerkUser(
        id=subject,
        email="owner@example.com",
        full_name="Shop Owner",
        email_verified=True,
    )


def _place_of(db_session: Session, shop: Shop) -> tuple[float, float]:
    """Where the shop ended up, as a latitude and a longitude."""
    row = db_session.execute(
        select(
            func.ST_Y(shop.location).label("lat"),
            func.ST_X(shop.location).label("lng"),
        )
    ).one()
    return float(row[0]), float(row[1])


def _onboard(client: TestClient, **body: object) -> object:
    return client.post(
        ONBOARDING,
        json={"role": "vendor", "shop_name": "Corner Prints", **body},
        headers=identity_headers(client, SUBJECT),
    )


def test_an_address_is_looked_up_and_the_shop_is_placed_there(
    client: TestClient, db_session: Session
) -> None:
    _tell_the_provider_about(client, SUBJECT)
    client.app.state.geocoder = MemoryGeocoder(
        {"3 example street": GeocodeResult(latitude=22.5726, longitude=88.3639)}
    )

    response = _onboard(client, shop_address="3 Example Street")

    assert response.status_code == 200, response.text
    shop = db_session.scalar(select(Shop).where(Shop.owner_id == response.json()["id"]))
    assert shop is not None
    assert _place_of(db_session, shop) == (22.5726, 88.3639)


def test_the_coordinates_the_owner_typed_are_used(client: TestClient, db_session: Session) -> None:
    """The owner's own coordinates win, and the map is not asked."""
    _tell_the_provider_about(client, SUBJECT)
    geocoder = MemoryGeocoder(
        {"3 example street": GeocodeResult(latitude=22.5726, longitude=88.3639)}
    )
    client.app.state.geocoder = geocoder

    response = _onboard(
        client,
        shop_address="3 Example Street",
        latitude=19.076,
        longitude=72.8777,
    )

    assert response.status_code == 200, response.text
    shop = db_session.scalar(select(Shop).where(Shop.owner_id == response.json()["id"]))
    assert shop is not None
    assert _place_of(db_session, shop) == (19.076, 72.8777)
    assert geocoder.asked == []


def test_a_deployment_without_a_geocoder_asks_for_the_coordinates(
    client: TestClient, db_session: Session
) -> None:
    """It says what is missing rather than failing later."""
    _tell_the_provider_about(client, SUBJECT)
    client.app.state.geocoder = None

    response = _onboard(client, shop_address="3 Example Street")

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "COORDINATES_REQUIRED"
    assert "latitude and longitude" in response.json()["error"]["message"]
    # Nothing was made, so there is no account without a shop.
    assert db_session.scalars(select(User)).all() == []


def test_an_address_that_cannot_be_found_leaves_no_account(
    client: TestClient, db_session: Session
) -> None:
    _tell_the_provider_about(client, SUBJECT)
    client.app.state.geocoder = MemoryGeocoder()

    response = _onboard(client, shop_address="Nowhere at all")

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "ADDRESS_NOT_FOUND"
    assert db_session.scalars(select(User)).all() == []
