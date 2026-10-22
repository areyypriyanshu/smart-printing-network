"""Asking Google where an address is.

The request is written with the standard library, so nothing is added
to the dependency list for one HTTP call that returns JSON.

The key is a secret and stays on the server. The browser never sees it:
the browser asks this server where a place is, and the server asks
Google. The key is the server's own, restricted by the API it may call
and by the address it may be called from.

Google is not the default any more, because the account asks for
billing. It stays here for a deployment that has a key and wants the
better matching of an Indian address.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.gateways.geocoding.base import Fetch, GeocodeError, GeocodeResult

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DEFAULT_TIMEOUT_SECONDS = 5.0


def _fetch_over_http(url: str, headers: dict[str, str], timeout: float) -> bytes:
    """The body at this address.

    The URL is built from a fixed host and a query that is encoded, so
    the address itself cannot carry anything the caller put in it.
    """
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body: bytes = response.read()
        return body


class GoogleGeocoder:
    """The geocoding provider this project uses when it has a key."""

    #: Google asks for an attribution when its maps are shown. No map is
    #: shown here, and the address on the shop is the owner's own
    #: words, so there is nothing of Google's to attribute.
    attribution = None

    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        fetch: Fetch | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._fetch = fetch if fetch is not None else _fetch_over_http

    def geocode(self, address: str) -> GeocodeResult | None:
        query = urllib.parse.urlencode({"address": address, "key": self._api_key})
        url = f"{GEOCODE_URL}?{query}"
        try:
            body = self._fetch(url, {"Accept": "application/json"}, self._timeout)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise GeocodeError(f"the geocoding provider could not be reached: {exc}") from exc
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GeocodeError(
                "the geocoding provider answered with something that is not JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise GeocodeError("the geocoding provider answered with something unexpected")
        return _read_result(payload)


def _read_result(payload: dict[str, Any]) -> GeocodeResult | None:
    status = payload.get("status")
    if status == "ZERO_RESULTS":
        # The provider was asked and it says there is no such place.
        # That is an answer, and not a fault.
        return None
    if status != "OK":
        # OVER_QUERY_LIMIT, REQUEST_DENIED and the rest are the
        # provider's way of saying it would not answer this time.
        raise GeocodeError(f"the geocoding provider answered {status}")
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        raise GeocodeError("the geocoding provider answered with something unexpected")
    geometry = first.get("geometry")
    location = geometry.get("location") if isinstance(geometry, dict) else None
    if not isinstance(location, dict):
        raise GeocodeError("the geocoding provider answered without a point")
    latitude = location.get("lat")
    longitude = location.get("lng")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise GeocodeError("the geocoding provider answered without a point")
    formatted = first.get("formatted_address")
    return GeocodeResult(
        latitude=float(latitude),
        longitude=float(longitude),
        formatted_address=formatted if isinstance(formatted, str) else "",
    )
