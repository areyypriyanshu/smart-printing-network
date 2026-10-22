"""Turning an address into a point.

The map provider is somebody else's database, and this project has to
get four things right about it: the point it reads is the point the
answer names, "there is no such place" and "the provider would not
answer" are told apart, the coordinates a shop owner typed beat a
lookup every time, and the rules the free provider asks for are kept.
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
    CachedGeocoder,
    GeocodeError,
    GeocodeResult,
    GoogleGeocoder,
    MemoryGeocoder,
    NominatimGeocoder,
    build_geocoder,
)
from app.gateways.geocoding.throttle import Throttle
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


# --------------------------------------------------------------------------
# Google, for a deployment that has a key
# --------------------------------------------------------------------------


def test_the_point_is_the_one_the_answer_names() -> None:
    """The latitude and the longitude are not the same thing.

    A provider that answers with the latitude first is not unusual, and
    a reader that swapped them would put every shop in the wrong part of
    the world.
    """
    geocoder = GoogleGeocoder(
        api_key="a-key", fetch=lambda url, headers, timeout: _ok_answer(22.58, 88.36)
    )

    point = geocoder.geocode("Salt Lake")

    assert point is not None
    assert point.latitude == 22.58
    assert point.longitude == 88.36


def test_the_request_carries_the_address_and_the_key() -> None:
    """The key is a secret and it goes in the query, not in the log."""
    seen: list[str] = []

    def fetch(url: str, headers: dict[str, str], timeout: float) -> bytes:
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
        api_key="a-key", fetch=lambda url, headers, timeout: _answer(status="ZERO_RESULTS")
    )

    assert geocoder.geocode("Nowhere at all") is None


def test_a_provider_that_will_not_answer_is_a_fault() -> None:
    geocoder = GoogleGeocoder(
        api_key="a-key", fetch=lambda url, headers, timeout: _answer(status="OVER_QUERY_LIMIT")
    )

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


def test_a_provider_that_cannot_be_reached_is_a_fault() -> None:
    def fetch(url: str, headers: dict[str, str], timeout: float) -> bytes:
        raise urllib.error.URLError("the name did not resolve")

    geocoder = GoogleGeocoder(api_key="a-key", fetch=fetch)

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


def test_an_answer_that_is_not_json_is_a_fault() -> None:
    geocoder = GoogleGeocoder(api_key="a-key", fetch=lambda url, headers, timeout: b"<html>")

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


def test_an_answer_without_a_point_is_a_fault() -> None:
    """An answer with no point in it cannot be used, and pretending
    otherwise would put a shop at the origin of the map."""
    geocoder = GoogleGeocoder(
        api_key="a-key",
        fetch=lambda url, headers, timeout: _answer(
            status="OK", results=[{"formatted_address": "x"}]
        ),
    )

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


# --------------------------------------------------------------------------
# OpenStreetMap, the free one
# --------------------------------------------------------------------------


def _nominatim_answer(latitude: str, longitude: str) -> bytes:
    return json.dumps(
        [
            {
                "place_id": "1",
                "lat": latitude,
                "lon": longitude,
                "display_name": "Salt Lake, Kolkata, India",
                "type": "suburb",
            }
        ]
    ).encode()


def test_the_openstreetmap_point_is_the_one_the_answer_names() -> None:
    """The answer has the point as text, and it is read as a number."""
    geocoder = NominatimGeocoder(
        user_agent="SmartPrintingNetwork/1.0 (+https://example.invalid)",
        fetch=lambda url, headers, timeout: _nominatim_answer("22.5812", "88.3633"),
    )

    point = geocoder.geocode("Salt Lake")

    assert point is not None
    assert point.latitude == 22.5812
    assert point.longitude == 88.3633


def test_the_request_says_which_application_is_asking() -> None:
    """The policy asks for a user agent that identifies the application,
    and the one a library sets by itself does not do."""
    seen: list[dict[str, str]] = []

    def fetch(url: str, headers: dict[str, str], timeout: float) -> bytes:
        seen.append(dict(headers))
        return _nominatim_answer("22.5812", "88.3633")

    NominatimGeocoder(
        user_agent="SmartPrintingNetwork/1.0 (+https://example.invalid)",
        fetch=fetch,
    ).geocode("Salt Lake")

    assert seen[0]["User-Agent"] == "SmartPrintingNetwork/1.0 (+https://example.invalid)"


def test_the_request_goes_to_the_instance_that_was_configured() -> None:
    """A deployment that runs its own instance changes one setting."""
    seen: list[str] = []

    def fetch(url: str, headers: dict[str, str], timeout: float) -> bytes:
        seen.append(url)
        return _nominatim_answer("22.5812", "88.3633")

    NominatimGeocoder(
        user_agent="SmartPrintingNetwork/1.0 (+https://example.invalid)",
        base_url="https://nominatim.example.invalid/",
        fetch=fetch,
    ).geocode("Salt Lake")

    assert seen[0].startswith("https://nominatim.example.invalid/search?")
    assert "q=Salt+Lake" in seen[0]


def test_an_address_nobody_has_heard_of_has_no_point_in_openstreetmap() -> None:
    """An empty list is an answer, and not a fault."""
    geocoder = NominatimGeocoder(
        user_agent="SmartPrintingNetwork/1.0 (+https://example.invalid)",
        fetch=lambda url, headers, timeout: b"[]",
    )

    assert geocoder.geocode("Nowhere at all") is None


def test_an_openstreetmap_answer_without_a_point_is_a_fault() -> None:
    geocoder = NominatimGeocoder(
        user_agent="SmartPrintingNetwork/1.0 (+https://example.invalid)",
        fetch=lambda url, headers, timeout: json.dumps([{"display_name": "x"}]).encode(),
    )

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


def test_an_openstreetmap_answer_with_a_point_off_the_earth_is_a_fault() -> None:
    geocoder = NominatimGeocoder(
        user_agent="SmartPrintingNetwork/1.0 (+https://example.invalid)",
        fetch=lambda url, headers, timeout: _nominatim_answer("999", "999"),
    )

    with pytest.raises(GeocodeError):
        geocoder.geocode("Salt Lake")


def test_the_openstreetmap_client_waits_for_its_turn() -> None:
    """The policy asks for one call a second from the whole
    application, so the throttle is consulted before the call."""
    waited: list[bool] = []

    class Recorder:
        def wait(self) -> None:
            waited.append(True)

    geocoder = NominatimGeocoder(
        user_agent="SmartPrintingNetwork/1.0 (+https://example.invalid)",
        throttle=Recorder(),  # type: ignore[arg-type]
        fetch=lambda url, headers, timeout: _nominatim_answer("22.5812", "88.3633"),
    )

    geocoder.geocode("Salt Lake")

    assert waited == [True]


def test_the_openstreetmap_answers_carry_the_attribution() -> None:
    """The policy asks for the attribution to be shown wherever the data
    is shown, and it is not optional."""
    geocoder = NominatimGeocoder(
        user_agent="SmartPrintingNetwork/1.0 (+https://example.invalid)",
    )

    assert geocoder.attribution is not None
    assert "OpenStreetMap" in geocoder.attribution


# --------------------------------------------------------------------------
# One call at a time
# --------------------------------------------------------------------------


def test_the_throttle_waits_between_calls() -> None:
    """Two calls close together are spaced out, not both sent."""
    now = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] = now[0] + seconds

    throttle = Throttle(min_interval_seconds=1.0, clock=lambda: now[0], sleep=sleep)

    throttle.wait()
    now[0] = 0.2
    throttle.wait()

    # The second call was held back for the rest of the second.
    assert slept == [pytest.approx(0.8)]


def test_the_throttle_does_not_wait_when_enough_time_has_passed() -> None:
    now = [0.0]
    slept: list[float] = []

    throttle = Throttle(
        min_interval_seconds=1.0,
        clock=lambda: now[0],
        sleep=lambda seconds: slept.append(seconds),
    )

    throttle.wait()
    now[0] = 5.0
    throttle.wait()

    assert slept == []


# --------------------------------------------------------------------------
# The answers are kept
# --------------------------------------------------------------------------


class _Counting:
    """A geocoder that counts what it was asked."""

    attribution = None

    def __init__(self, answer: GeocodeResult | None = None, *, found: bool = True) -> None:
        self.answer = answer if found else None
        self.asked: list[str] = []

    def geocode(self, address: str) -> GeocodeResult | None:
        self.asked.append(address)
        return self.answer


def test_the_same_address_is_asked_only_once() -> None:
    """The policy asks for the answers to be cached, and it saves a call
    that somebody else pays for."""
    provider = _Counting()
    cache = CachedGeocoder(provider)

    cache.geocode("Salt Lake")
    cache.geocode("  salt   lake ")

    assert provider.asked == ["Salt Lake"]


def test_an_address_with_no_point_is_kept_too() -> None:
    """It was an answer, and asking again would ask the same question."""
    provider = _Counting(found=False)
    cache = CachedGeocoder(provider)

    assert cache.geocode("Nowhere at all") is None
    assert cache.geocode("Nowhere at all") is None

    assert provider.asked == ["Nowhere at all"]


def test_an_old_answer_is_asked_again() -> None:
    """The cache is a cache, and not a record."""
    now = [0.0]
    provider = _Counting()
    cache = CachedGeocoder(provider, ttl_seconds=60.0, clock=lambda: now[0])

    cache.geocode("Salt Lake")
    now[0] = 120.0
    cache.geocode("Salt Lake")

    assert provider.asked == ["Salt Lake", "Salt Lake"]


def test_the_cache_does_not_grow_without_end() -> None:
    cache = CachedGeocoder(_Counting(), max_entries=3)

    for index in range(10):
        cache.geocode(f"place {index}")

    assert len(cache._entries) == 3


# --------------------------------------------------------------------------
# Which provider this deployment uses
# --------------------------------------------------------------------------


def test_the_free_provider_is_the_default() -> None:
    """No key, no account, no bill."""
    geocoder = build_geocoder(_settings())

    assert geocoder is not None
    assert "OpenStreetMap" in (geocoder.attribution or "")


def test_a_deployment_can_have_no_geocoder_at_all() -> None:
    """The platform works without one: the shop owner types the
    coordinates and the customer sees the whole list."""
    assert build_geocoder(_settings(geocoding_provider="none")) is None


def test_the_commercial_provider_needs_its_key() -> None:
    with pytest.raises(ValueError, match="GOOGLE_GEOCODING_API_KEY"):
        build_geocoder(_settings(geocoding_provider="google"))


def test_the_commercial_provider_is_used_when_it_is_configured() -> None:
    geocoder = build_geocoder(
        _settings(geocoding_provider="google", google_geocoding_api_key="a-key")
    )

    assert isinstance(geocoder, CachedGeocoder)
    assert geocoder.attribution is None


def test_an_unknown_provider_is_refused() -> None:
    with pytest.raises(ValueError, match="GEOCODING_PROVIDER"):
        build_geocoder(_settings(geocoding_provider="carrier-pigeon"))


# --------------------------------------------------------------------------
# What the application does with the answer
# --------------------------------------------------------------------------


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
