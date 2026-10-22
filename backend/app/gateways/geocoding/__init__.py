from app.config import Settings
from app.gateways.geocoding.base import GeocodeError, Geocoder, GeocodeResult
from app.gateways.geocoding.google import GoogleGeocoder
from app.gateways.geocoding.memory import MemoryGeocoder

__all__ = [
    "GeocodeError",
    "GeocodeResult",
    "Geocoder",
    "GoogleGeocoder",
    "MemoryGeocoder",
    "build_geocoder",
]


def build_geocoder(settings: Settings) -> Geocoder | None:
    """The geocoder this deployment uses, if it has one.

    There is no key, there is no geocoder. A deployment that has not
    been given a key still works: a shop owner types the coordinates
    of their shop, and a customer who cannot share a location sees the
    whole list. Nothing is a fault except the search for a typed
    address, which is refused with a message that says why.
    """
    key = settings.google_geocoding_api_key.strip()
    if not key:
        return None
    return GoogleGeocoder(api_key=key)
