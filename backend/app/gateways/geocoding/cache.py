"""Answers that have already been given.

The public OpenStreetMap geocoder asks for the answers to be cached on
our side, and it is the right thing to do anyway: the same address is
looked up again every time somebody registers a shop, and a lookup is
a call somebody else pays for.

An address that had no point is cached too. It was an answer, and
asking again would only ask the same question.

Two people asking for the same address at the same time make one call
between them, not two. The policy is explicit that "clients sending
repeatedly the same query may be classified as faulty and blocked", so
the second caller waits for the first answer rather than asking the
provider again.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.gateways.geocoding.base import Geocoder, GeocodeResult


@dataclass(frozen=True)
class _Entry:
    result: GeocodeResult | None
    stored_at: float


class CachedGeocoder:
    """Answers from a table of what has already been asked.

    The table is in the process, so it is empty again after a restart.
    That is fine: it is a cache, not a record.
    """

    def __init__(
        self,
        inner: Geocoder,
        *,
        ttl_seconds: float = 3600.0,
        max_entries: int = 500,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}
        # One lock per address, so that the second caller for an
        # address waits for the first answer instead of asking again.
        self._calls: dict[str, threading.Lock] = {}

    @property
    def attribution(self) -> str | None:
        return self._inner.attribution

    @property
    def inner(self) -> Geocoder:
        """The geocoder this one answers for."""
        return self._inner

    def geocode(self, address: str) -> GeocodeResult | None:
        key = " ".join(address.split()).lower()

        with self._lock:
            known = self._known(key)
            if known is not None:
                return known.result
            call_lock = self._calls.setdefault(key, threading.Lock())

        with call_lock:
            # Somebody else may have asked while this one waited.
            with self._lock:
                known = self._known(key)
                if known is not None:
                    return known.result
            result = self._inner.geocode(address)
            with self._lock:
                self._entries[key] = _Entry(result=result, stored_at=self._clock())
                self._drop_the_oldest()
            return result

    def _known(self, key: str) -> _Entry | None:
        """The entry we already have, if it is still fresh.

        The entry is returned rather than the answer, because "no such
        place" is an answer too and it has to be told apart from
        "nothing yet".
        """
        entry = self._entries.get(key)
        if entry is None:
            return None
        if self._clock() - entry.stored_at >= self._ttl:
            return None
        return entry

    def _drop_the_oldest(self) -> None:
        """Keep the table from growing without end."""
        while len(self._entries) > self._max_entries:
            oldest = min(self._entries.items(), key=lambda item: item[1].stored_at)
            del self._entries[oldest[0]]
            self._calls.pop(oldest[0], None)
