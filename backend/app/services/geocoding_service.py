"""Finding a point for an address.

Two things need a point. A shop needs one, so that a customer can find
it. A typed address needs one, so that a customer who will not share a
location can still search around somewhere.

Both go through the same door: the geocoding provider. What happens
when there is no provider is the interesting part. A deployment that
has not been given a key still works. A shop owner types the
coordinates of their shop by hand, and a customer who cannot share a
location sees the whole list. Only the search for a typed address is
refused, and it is refused with a message that says why.
"""

from app.errors import (
    AddressNotFound,
    CoordinatesRequired,
    GeocodingUnavailable,
    ValidationError,
)
from app.gateways.geocoding import GeocodeError, Geocoder, GeocodeResult


def geocode(geocoder: Geocoder | None, address: str) -> GeocodeResult:
    """The point for an address.

    Three answers are possible and they are told apart: a point, an
    address nobody has heard of, and a provider that would not answer.
    The first is what the caller wanted. The second is the caller's to
    fix. The third is worth trying again later, and saying so matters
    more than the code does.
    """
    if geocoder is None:
        raise GeocodingUnavailable(
            "This deployment cannot look up an address. Ask the browser for your location instead."
        )
    try:
        result = geocoder.geocode(address)
    except GeocodeError as exc:
        raise GeocodingUnavailable(
            "The map provider could not be reached. Try again in a moment."
        ) from exc
    if result is None:
        raise AddressNotFound(
            "We could not find that address. Try a nearby area or a well known place."
        )
    return result


def resolve_shop_point(
    geocoder: Geocoder | None,
    *,
    address: str,
    latitude: float | None,
    longitude: float | None,
) -> tuple[float, float]:
    """Where a shop is, from what its owner gave or from what we looked up.

    The coordinates the owner typed come first. They are what the owner
    knows, and a shop owner knows where their own shop is better than a
    map does, which will happily put a shop in the middle of a lake
    because the address on the letter is short.

    Only when there are no coordinates is the address looked up. A
    deployment with no geocoding provider cannot do that, so it says
    so and asks for the coordinates.
    """
    if latitude is not None and longitude is not None:
        return latitude, longitude
    if latitude is not None or longitude is not None:
        raise ValidationError("Give a latitude and a longitude, or neither.")
    if geocoder is None:
        raise CoordinatesRequired(
            "Give the shop's latitude and longitude, because this deployment "
            "cannot look an address up on the map."
        )
    point = geocode(geocoder, address)
    return point.latitude, point.longitude
