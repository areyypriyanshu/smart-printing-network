"""Turning an address into a point on the earth.

The gateway is an interface for the same reason the payment gateway and
the mail gateway are: the application must not know which provider
answers, and the answer must be replaceable in a test without a
network.

An address in this application is a string a person typed. A point is a
latitude and a longitude. The conversion between them is somebody
else's database, and it is not always able to answer: an address that
nobody has heard of has no point, and that is not a fault.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

#: How a body is fetched: the address, the headers to send with it, and
#: how long to wait. The default goes to the network; a test passes its
#: own, so the test suite never leaves the machine.
Fetch = Callable[[str, Mapping[str, str], float], bytes]


class GeocodeError(RuntimeError):
    """The geocoding provider could not be asked.

    This is a fault in a dependency rather than anything the caller did,
    so it is not the same thing as an address that has no point. The
    difference matters: an address that cannot be found is the caller's
    to fix, and a provider that cannot be reached is worth retrying.
    """


@dataclass(frozen=True)
class GeocodeResult:
    """One point, and the address the provider read it from."""

    latitude: float
    longitude: float
    formatted_address: str = ""


class Geocoder(Protocol):
    """Turns an address into a point."""

    @property
    def attribution(self) -> str | None:
        """What has to be shown to a person when the data this provider
        gave is shown to them.

        OpenStreetMap asks for that, and it is not optional. `None`
        means there is nothing to say.
        """
        ...

    def geocode(self, address: str) -> GeocodeResult | None:
        """The point for `address`, or `None` when there is no such point.

        Raise `GeocodeError` when the provider could not be reached. The
        two are different: one is an answer and the other is a fault.
        """
        ...
