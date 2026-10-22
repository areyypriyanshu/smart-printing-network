"""A geocoder that answers from a table the test wrote down.

There is no network in the test suite, and there is no reason for one:
a search test needs to know where an address is, and a table says so
exactly. The addresses are matched without regard to case and to the
spaces around them, because a person types "  Salt Lake " and means
"Salt Lake".
"""

from app.gateways.geocoding.base import GeocodeError, GeocodeResult


class MemoryGeocoder:
    """Answers from a dictionary."""

    def __init__(self, results: dict[str, GeocodeResult] | None = None) -> None:
        self._results = {self._key(address): point for address, point in (results or {}).items()}
        #: Every address that was asked about, in order.
        self.asked: list[str] = []
        #: When this is set, every question raises it. It is how a test
        #: says "the provider is down" without a network.
        self.failure: GeocodeError | None = None

    def geocode(self, address: str) -> GeocodeResult | None:
        self.asked.append(address)
        if self.failure is not None:
            raise self.failure
        return self._results.get(self._key(address))

    @staticmethod
    def _key(address: str) -> str:
        return " ".join(address.split()).lower()
