from app.config import Settings
from app.gateways.geocoding.base import Fetch, GeocodeError, Geocoder, GeocodeResult
from app.gateways.geocoding.cache import CachedGeocoder
from app.gateways.geocoding.google import GoogleGeocoder
from app.gateways.geocoding.memory import MemoryGeocoder
from app.gateways.geocoding.nominatim import OSM_ATTRIBUTION, NominatimGeocoder
from app.gateways.geocoding.throttle import Throttle

__all__ = [
    "Fetch",
    "GeocodeError",
    "GeocodeResult",
    "Geocoder",
    "CachedGeocoder",
    "GoogleGeocoder",
    "MemoryGeocoder",
    "NominatimGeocoder",
    "OSM_ATTRIBUTION",
    "Throttle",
    "build_geocoder",
]

#: The providers this application knows how to ask.
PROVIDERS = ("nominatim", "google", "none")


def build_geocoder(settings: Settings) -> Geocoder | None:
    """The geocoder this deployment uses, if it has one.

    The free one is the default: OpenStreetMap's public instance needs
    no key and no account, and its policy asks for four things that are
    done here — one call a second for the whole application, a user
    agent that says who is asking, the answers cached, and the
    attribution shown.

    A deployment that would rather not depend on a donated service sets
    the provider to `none`. Then a shop owner types the coordinates of
    their shop, and a customer who cannot share a location sees the
    whole list.
    """
    provider = settings.geocoding_provider.strip().lower()
    if provider == "none":
        return None
    if provider == "google":
        key = settings.google_geocoding_api_key.strip()
        if not key:
            raise ValueError("GOOGLE_GEOCODING_API_KEY is required when GEOCODING_PROVIDER=google")
        return CachedGeocoder(GoogleGeocoder(api_key=key))
    if provider == "nominatim":
        return CachedGeocoder(
            NominatimGeocoder(
                user_agent=settings.geocoding_user_agent,
                base_url=settings.nominatim_base_url,
                throttle=Throttle(min_interval_seconds=settings.geocoding_min_interval),
            )
        )
    raise ValueError(
        f"Unknown GEOCODING_PROVIDER: {settings.geocoding_provider!r}. "
        f"Use one of {', '.join(PROVIDERS)}."
    )
