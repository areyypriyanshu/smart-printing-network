"""Asking OpenStreetMap where an address is.

The public instance of Nominatim is free and needs no key, and it is
run on donated servers. Its usage policy asks for four things, and this
client does all four:

- no more than one request a second from the whole application, which
  is the `Throttle` in front of the call;
- a User-Agent that says which application is asking, rather than the
  one a library sets by itself;
- the answers cached on our side, which is the `CachedGeocoder` around
  this client;
- the attribution shown to the person who sees the data.

The data is OpenStreetMap's, under the ODbL. It is good enough to find
an area like "Salt Lake" and to place a well known street address. It
is not as good as a commercial provider at guessing which shop is at
"12 Esplanade Row", and the application says so by letting the shop
owner type the coordinates instead.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.gateways.geocoding.base import Fetch, GeocodeError, GeocodeResult
from app.gateways.geocoding.throttle import Throttle

DEFAULT_BASE_URL = "https://nominatim.openstreetmap.org"
DEFAULT_TIMEOUT_SECONDS = 10.0

#: What has to be shown to a person when this provider's data is shown
#: to them. The policy asks for it, and it is not optional.
OSM_ATTRIBUTION = "© OpenStreetMap contributors"


def _fetch_over_http(url: str, headers: dict[str, str], timeout: float) -> bytes:
    """The body at this address.

    The URL is built from a fixed host and a query that is encoded, so
    the address itself cannot carry anything the caller put in it.
    """
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body: bytes = response.read()
        return body


class NominatimGeocoder:
    """The free geocoder this project uses by default."""

    attribution = OSM_ATTRIBUTION

    def __init__(
        self,
        *,
        user_agent: str,
        base_url: str = DEFAULT_BASE_URL,
        throttle: Throttle | None = None,
        fetch: Fetch | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._user_agent = user_agent
        self._base_url = base_url.rstrip("/")
        self._throttle = throttle
        self._fetch = fetch if fetch is not None else _fetch_over_http
        self._timeout = timeout

    @property
    def throttle(self) -> Throttle | None:
        """The rule that keeps this application inside its share of the
        service. It is None only when the client is used on its own,
        which is what the tests do."""
        return self._throttle

    def geocode(self, address: str) -> GeocodeResult | None:
        query = urllib.parse.urlencode(
            {"q": address, "format": "jsonv2", "limit": 1, "addressdetails": 0}
        )
        url = f"{self._base_url}/search?{query}"
        headers = {"Accept": "application/json", "User-Agent": self._user_agent}
        if self._throttle is not None:
            # One call at a time, from the whole application. The policy
            # asks for it and the service is run on donated servers.
            self._throttle.wait()
        try:
            body = self._fetch(url, headers, self._timeout)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise GeocodeError(f"the geocoding provider could not be reached: {exc}") from exc
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GeocodeError(
                "the geocoding provider answered with something that is not JSON"
            ) from exc
        if not isinstance(payload, list):
            raise GeocodeError("the geocoding provider answered with something unexpected")
        return _read_result(payload)


def _read_result(payload: list[Any]) -> GeocodeResult | None:
    """The first answer, or nothing at all.

    Nominatim answers with an empty list when it has not heard of the
    place, which is an answer and not a fault.
    """
    if not payload:
        return None
    first = payload[0]
    if not isinstance(first, dict):
        raise GeocodeError("the geocoding provider answered with something unexpected")
    latitude = first.get("lat")
    longitude = first.get("lon")
    if not isinstance(latitude, str) or not isinstance(longitude, str):
        raise GeocodeError("the geocoding provider answered without a point")
    try:
        latitude_value = float(latitude)
        longitude_value = float(longitude)
    except ValueError as exc:
        raise GeocodeError("the geocoding provider answered without a point") from exc
    if not (-90.0 <= latitude_value <= 90.0) or not (-180.0 <= longitude_value <= 180.0):
        raise GeocodeError("the geocoding provider answered with a point that is not on the earth")
    display = first.get("display_name")
    return GeocodeResult(
        latitude=latitude_value,
        longitude=longitude_value,
        formatted_address=display if isinstance(display, str) else "",
    )
