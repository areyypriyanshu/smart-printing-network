"""The shops around a point, and what they would charge.

The customer wants a shop near them and the price for their job, side
by side. Two things have to be right: the place on the map, which is
where the shop actually is, and the price, which has to be the price
the customer is charged when they order.
"""

import uuid

from app.gateways.geocoding import GeocodeResult, MemoryGeocoder
from app.gateways.payments import FakeGateway
from app.models import ShopRate
from app.schemas.order import OrderCreateRequest
from app.services import order_service
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import (
    FAKE_WEBHOOK_SECRET,
    create_full_rate_table,
    create_shop,
    create_upload_row,
    create_user,
    login_headers,
)

SEARCH = "/api/v1/shops/search"

#: A point in central Kolkata, and the three seeded shops around it.
CENTRAL_LATITUDE = 22.5726
CENTRAL_LONGITUDE = 88.3639


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


def _search(
    client: TestClient,
    headers: dict[str, str],
    **params: object,
) -> dict:
    response = client.get(SEARCH, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_nearest_shop_comes_first(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    body = _search(
        client,
        headers,
        latitude=CENTRAL_LATITUDE,
        longitude=CENTRAL_LONGITUDE,
        radius_m=50000,
    )

    items = body["items"]
    # The far shop is a thousand kilometres away, so it is not nearby.
    assert [item["name"] for item in items] == [
        "Close Shop",
        "Another Close Shop",
        "Middle Shop",
    ]
    assert items[0]["distance_m"] < items[1]["distance_m"]
    assert items[1]["distance_m"] < items[2]["distance_m"]


def test_the_distance_is_measured_in_metres(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    body = _search(
        client,
        headers,
        latitude=CENTRAL_LATITUDE,
        longitude=CENTRAL_LONGITUDE,
        radius_m=50000,
    )

    close = next(item for item in body["items"] if item["name"] == "Close Shop")
    # About fifty metres from the point, give or take the curvature.
    assert 0 < close["distance_m"] < 200


def test_the_latitude_and_the_longitude_are_not_swapped(
    client: TestClient, db_session: Session
) -> None:
    """The point is built with the longitude first, and the other way
    round is a different place on the earth.

    A shop a hundred and eleven metres north of the point has to be
    about a hundred and eleven metres away. If the two were swapped the
    shop would be on the other side of the world, or the database would
    refuse the point altogether.
    """
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    create_shop(
        db_session,
        owner=vendor,
        name="North Shop",
        latitude=CENTRAL_LATITUDE + 0.001,
        longitude=CENTRAL_LONGITUDE,
    )
    headers = login_headers(client, "customer@example.com")

    body = _search(
        client,
        headers,
        latitude=CENTRAL_LATITUDE,
        longitude=CENTRAL_LONGITUDE,
        radius_m=50000,
    )

    assert customer is not None
    assert len(body["items"]) == 1
    # A thousandth of a degree of latitude is about 111 metres.
    assert 100 < body["items"][0]["distance_m"] < 125


def test_a_shop_outside_the_radius_is_absent(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    body = _search(
        client,
        headers,
        latitude=CENTRAL_LATITUDE,
        longitude=CENTRAL_LONGITUDE,
        radius_m=2000,
    )

    names = [item["name"] for item in body["items"]]
    assert "Close Shop" in names
    assert "Far Shop" not in names


def test_an_unverified_shop_is_absent(client: TestClient, db_session: Session) -> None:
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

    body = _search(
        client,
        headers,
        latitude=CENTRAL_LATITUDE,
        longitude=CENTRAL_LONGITUDE,
        radius_m=50000,
    )

    assert "Unverified Shop" not in [item["name"] for item in body["items"]]


def test_a_shop_that_is_not_taking_orders_is_absent(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    vendor = create_user(db_session, email="second@example.com", role="vendor")
    create_shop(
        db_session,
        owner=vendor,
        name="Closed Shop",
        latitude=22.5727,
        longitude=88.3641,
        accepting_orders=False,
    )
    headers = login_headers(client, "customer@example.com")

    body = _search(
        client,
        headers,
        latitude=CENTRAL_LATITUDE,
        longitude=CENTRAL_LONGITUDE,
        radius_m=50000,
    )

    assert "Closed Shop" not in [item["name"] for item in body["items"]]


def test_the_price_is_the_price_that_would_be_charged(
    client: TestClient, db_session: Session
) -> None:
    """What the customer is shown is what the customer is charged.

    The comparison and the order use the same function, so this test
    creates a real order and compares the two numbers.
    """
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop, base_paise=200)
    upload = create_upload_row(db_session, customer=customer, page_count=5)
    headers = login_headers(client, "customer@example.com")

    body = _search(
        client,
        headers,
        latitude=22.5726,
        longitude=88.3639,
        radius_m=50000,
        upload_id=str(upload.id),
        paper_size="A4",
        color=False,
        duplex=False,
        copies=2,
    )

    assert len(body["items"]) == 1
    assert body["items"][0]["price_paise"] == 5 * 2 * 200

    order, _payment = order_service.create_order(
        db_session,
        customer_id=customer.id,
        request=OrderCreateRequest(
            upload_id=upload.id,
            shop_id=shop.id,
            paper_size="A4",
            color=False,
            duplex=False,
            copies=2,
        ),
        idempotency_key=uuid.uuid4().hex,
        gateway=FakeGateway(webhook_secret=FAKE_WEBHOOK_SECRET),
    )
    assert order.price_paise == body["items"][0]["price_paise"]


def test_the_minimum_order_is_applied_to_the_price(client: TestClient, db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor, min_order_paise=5000)
    create_full_rate_table(db_session, shop, base_paise=100)
    upload = create_upload_row(db_session, customer=customer, page_count=1)
    headers = login_headers(client, "customer@example.com")

    body = _search(
        client,
        headers,
        latitude=22.5726,
        longitude=88.3639,
        radius_m=50000,
        upload_id=str(upload.id),
        paper_size="A4",
        color=False,
        duplex=False,
        copies=1,
    )

    assert body["items"][0]["price_paise"] == 5000


def test_a_shop_that_does_not_offer_the_options_is_left_out(
    client: TestClient, db_session: Session
) -> None:
    """A comparison of shops that cannot do the job is not a comparison."""
    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    offers_a4 = create_shop(db_session, owner=vendor, name="A4 Shop")
    create_full_rate_table(db_session, offers_a4, base_paise=200)
    second = create_user(db_session, email="vendor2@example.com", role="vendor")
    only_a3 = create_shop(db_session, owner=second, name="A3 Shop")
    db_session.add(
        ShopRate(shop_id=only_a3.id, paper_size="A3", color=False, duplex=False, rate_paise=100)
    )
    db_session.commit()
    upload = create_upload_row(db_session, customer=customer, page_count=1)
    headers = login_headers(client, "customer@example.com")

    body = _search(
        client,
        headers,
        latitude=22.5726,
        longitude=88.3639,
        radius_m=50000,
        upload_id=str(upload.id),
        paper_size="A4",
        color=False,
        duplex=False,
        copies=1,
    )

    assert [item["name"] for item in body["items"]] == ["A4 Shop"]


def test_the_cheapest_shop_comes_first(client: TestClient, db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    for index, (name, base) in enumerate(
        [("Pricey Shop", 800), ("Cheap Shop", 100), ("Middle Shop", 400)]
    ):
        vendor = create_user(db_session, email=f"vendor{index}@example.com", role="vendor")
        shop = create_shop(db_session, owner=vendor, name=name)
        create_full_rate_table(db_session, shop, base_paise=base)
    upload = create_upload_row(db_session, customer=customer, page_count=1)
    headers = login_headers(client, "customer@example.com")

    body = _search(
        client,
        headers,
        latitude=22.5726,
        longitude=88.3639,
        radius_m=50000,
        upload_id=str(upload.id),
        paper_size="A4",
        color=False,
        duplex=False,
        copies=1,
        sort="price",
    )

    assert [item["name"] for item in body["items"]] == [
        "Cheap Shop",
        "Middle Shop",
        "Pricey Shop",
    ]
    prices = [item["price_paise"] for item in body["items"]]
    assert prices == sorted(prices)


def test_sorting_by_price_without_a_file_is_refused(
    client: TestClient, db_session: Session
) -> None:
    """A price needs a file and the options, because there is nothing
    else to price."""
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.get(
        SEARCH,
        params={
            "latitude": CENTRAL_LATITUDE,
            "longitude": CENTRAL_LONGITUDE,
            "sort": "price",
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_sorting_by_distance_without_a_place_is_refused(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.get(SEARCH, params={"sort": "distance"}, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_every_shop_is_returned_when_the_customer_says_no_place(
    client: TestClient, db_session: Session
) -> None:
    """A customer who will not share a location still gets the list."""
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    body = _search(client, headers)

    assert len(body["items"]) == 4
    assert all(item["distance_m"] is None for item in body["items"])


def test_the_search_needs_authentication(client: TestClient, db_session: Session) -> None:
    _seed(db_session)

    response = client.get(
        SEARCH, params={"latitude": CENTRAL_LATITUDE, "longitude": CENTRAL_LONGITUDE}
    )

    assert response.status_code == 401, response.text


def test_a_vendor_cannot_search_for_shops(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    headers = login_headers(client, "vendor0@example.com")

    response = client.get(
        SEARCH,
        params={"latitude": CENTRAL_LATITUDE, "longitude": CENTRAL_LONGITUDE},
        headers=headers,
    )

    assert response.status_code == 403, response.text


def test_another_customers_file_is_not_used_for_a_price(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="owner@example.com")
    create_user(db_session, email="snooper@example.com")
    upload = create_upload_row(db_session, customer=owner, page_count=1)
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    headers = login_headers(client, "snooper@example.com")

    response = client.get(
        SEARCH,
        params={
            "latitude": 22.5726,
            "longitude": 88.3639,
            "upload_id": str(upload.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
        headers=headers,
    )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_the_options_have_to_go_together(client: TestClient, db_session: Session) -> None:
    """A paper size without a file is not a price, and the query says
    so instead of guessing."""
    _seed(db_session)
    headers = login_headers(client, "customer@example.com")

    response = client.get(SEARCH, params={"paper_size": "A4", "color": False}, headers=headers)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_typed_address_is_looked_up(client: TestClient, db_session: Session) -> None:
    """A customer who will not share a location can type where they are."""
    _seed(db_session)
    client.app.state.geocoder = MemoryGeocoder(
        {"salt lake": GeocodeResult(latitude=22.5726, longitude=88.3639)}
    )
    headers = login_headers(client, "customer@example.com")

    body = _search(client, headers, address="Salt Lake", radius_m=50000)

    assert [item["name"] for item in body["items"]] == [
        "Close Shop",
        "Another Close Shop",
        "Middle Shop",
    ]


def test_an_address_that_is_not_found_is_refused(client: TestClient, db_session: Session) -> None:
    """It is the caller's to fix: a different address."""
    _seed(db_session)
    client.app.state.geocoder = MemoryGeocoder()
    headers = login_headers(client, "customer@example.com")

    response = client.get(SEARCH, params={"address": "Nowhere at all"}, headers=headers)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "ADDRESS_NOT_FOUND"


def test_a_deployment_without_a_geocoder_says_so(client: TestClient, db_session: Session) -> None:
    """A deployment with no key cannot look an address up, and it says
    so rather than pretending the address does not exist."""
    _seed(db_session)
    client.app.state.geocoder = None
    headers = login_headers(client, "customer@example.com")

    response = client.get(SEARCH, params={"address": "Salt Lake"}, headers=headers)

    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "GEOCODING_UNAVAILABLE"
