"""Turning an address into a point.

The map provider is somebody else's database, and this project has to
get three things right about it: the point it reads is the point the
answer names, "there is no such place" and "the provider would not
answer" are told apart, and the coordinates a shop owner typed beat a
lookup every time.
"""

import json
import urllib.error

import pytest
from app.config import Settings
from app.errors import (
    AddressNotFound,
    CoordinatesRequired,
    GeocodingUnavailable,
    ValidationError,
)
from app.gateways.geocoding import (
    GeocodeError,
    GeocodeResult,
    GoogleGeocoder,
    MemoryGeocoder,
    build_geocoder,
)
from app.services.geocoding_service import geocode, resolve_shop_point

#: The settings a test starts from. The identity provider is always
#: needed, because there is one way to sign in.
BASE: dict[str, object] = {
    "env": "local",
    "payment_provider": "fake",
    "fake_webhook_secret": "a-key-the-operator-chose",
    "testing_endpoints_enabled": False,
    "clerk_fapi_url": "https://app.accounts.dev",
    "clerk_allowed_origins": "http://localhost:5173",
    "clerk_secret_key": "a-secret-the-operator-chose",
    "clerk_webhook_signing_secret": "whsec_another-secret-the-operator-chose",
    "spn_dev_auth": False,
}


def _settings(**overrides: object) -> Settings:
    values = {**BASE, **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _answer(**payload: object) -> bytes:
    return json.dumps(payload).encode()


def _ok_answer(latitude: float, longitude: float) -> bytes:
    return _answer(
        status="OK",
        results=[
            {
                "formatted_address": "Salt Lake, Kolkata",
                "geometry": {"location": {"lat": latitude, "lng": longitude}},
            }
        ],
    )


def test_the_point_is_the_one_the_answer_names() -> None:
    """The latitude and the longitude are not the same thing.

    A provider that answers with the latitude first is not unusual, and
    a reader that swapped them would put every shop in the wrong part of
    the world.
    """
    geocoder = GoogleGeocoder(api_key="a-key", fetch=lambda url, timeout: _ok_answer(22.58, 88.36))

    point = geocoder.geocode("Salt Lake")

    assert point is not None
    assert point.latitude == 22.58
    assert point.longitude == 88.36


def test_the_request_carries_the_address_and_the_key() -> None:
    """The key is a secret and it goes in the query, not in the log."""
    seen: list[str] = []

    def fetch(url: str, timeout: float) -> bytes:
        seen.append(url)
        return _ok_answer(22.58, 88.36)

    GoogleGeocoder(api_key="the-secret-key", fetch=fetch).geocode("Salt Lake Sector V")

    assert len(seen) == 1
    assert "the-secret-key" in seen[0]
    # The address is encoded, so a space is a space and not a plus that
    # the provider has to guess at.
    assert "Salt+Lake+Sector+V" in seen[0]


def test_an_address_nobody_has_heard_of_has_no_point() -> None:
    """No results is an answer, and not a fault."""
    geocoder = GoogleGeocoder(
        api_key="a-key", fetch=lambda url, timeout: _answer(status="ZERO_RESULTS")
    )

    assert geocoder.geocode("Nowhere at all") is None


def test_a_provider_that_will_not_answer_is_a_fault() -> None:
    geocoder = GoogleGeocoder(
        api_key="a-key", fetch=lambda url, timeout: _answer(status="OVER_QUERY_LIMIT")
    )

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


def test_a_provider_that_cannot_be_reached_is_a_fault() -> None:
    def fetch(url: str, timeout: float) -> bytes:
        raise urllib.error.URLError("the name did not resolve")

    geocoder = GoogleGeocoder(api_key="a-key", fetch=fetch)

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


def test_an_answer_that_is_not_json_is_a_fault() -> None:
    geocoder = GoogleGeocoder(api_key="a-key", fetch=lambda url, timeout: b"<html>")

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


def test_an_answer_without_a_point_is_a_fault() -> None:
    """An answer with no point in it cannot be used, and pretending
    otherwise would put a shop at the origin of the map."""
    geocoder = GoogleGeocoder(
        api_key="a-key",
        fetch=lambda url, timeout: _answer(status="OK", results=[{"formatted_address": "x"}]),
    )

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


def test_a_deployment_without_a_key_has_no_geocoder() -> None:
    """No key, no geocoder, and the application says so rather than
    failing later."""
    assert build_geocoder(_settings()) is None


def test_a_deployment_with_a_key_has_a_geocoder() -> None:
    geocoder = build_geocoder(_settings(google_geocoding_api_key="a-key"))

    assert isinstance(geocoder, GoogleGeocoder)


def test_an_address_that_cannot_be_found_is_refused() -> None:
    """It is the caller's to fix: a different address."""
    with pytest.raises(AddressNotFound):
        geocode(MemoryGeocoder(), "Nowhere at all")


def test_a_deployment_without_a_geocoder_cannot_look_an_address_up() -> None:
    """It is a different problem from an address that does not exist,
    and it has a different fix."""
    with pytest.raises(GeocodingUnavailable):
        geocode(None, "Salt Lake")


def test_a_provider_that_is_down_is_not_an_address_that_is_missing() -> None:
    geocoder = MemoryGeocoder()
    geocoder.failure = GeocodeError("the provider is down")

    with pytest.raises(GeocodingUnavailable):
        geocode(geocoder, "Salt Lake")


def test_the_coordinates_the_owner_typed_are_the_coordinates() -> None:
    """A shop owner knows where their own shop is."""
    geocoder = MemoryGeocoder({"Salt Lake": GeocodeResult(22.58, 88.36)})

    latitude, longitude = resolve_shop_point(
        geocoder, address="Salt Lake", latitude=19.07, longitude=72.87
    )

    assert (latitude, longitude) == (19.07, 72.87)
    # The lookup never happened, because it was not needed.
    assert geocoder.asked == []


def test_the_address_is_looked_up_when_there_are_no_coordinates() -> None:
    geocoder = MemoryGeocoder({"salt lake": GeocodeResult(22.58, 88.36)})

    latitude, longitude = resolve_shop_point(
        geocoder, address="Salt Lake", latitude=None, longitude=None
    )

    assert (latitude, longitude) == (22.58, 88.36)
    assert geocoder.asked == ["Salt Lake"]


def test_half_a_point_is_refused() -> None:
    """A latitude without a longitude is not a place."""
    with pytest.raises(ValidationError):
        resolve_shop_point(None, address="Salt Lake", latitude=22.58, longitude=None)


def test_a_deployment_without_a_geocoder_asks_for_the_coordinates() -> None:
    with pytest.raises(CoordinatesRequired, match="latitude and longitude"):
        resolve_shop_point(None, address="Salt Lake", latitude=None, longitude=None)
