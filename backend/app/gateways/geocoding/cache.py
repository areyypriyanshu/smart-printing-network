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

The waiting is done with an event rather than with a lock, because a
lock that is thrown away while somebody is waiting on it lets the next
caller in beside them, and then there are two calls after all.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.gateways.geocoding.base import Geocoder, GeocodeResult

#: How long a caller waits for the answer to somebody else's call
#: before it gives up and asks the provider itself. The providers time
#: out after five and ten seconds, so this is longer than any call
#: that is still running, and the second call cannot happen.
_WAIT_SECONDS = 15.0


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
        # The calls that are on their way. One per address, and only as
        # many as there are calls happening at the same time.
        self._inflight: dict[str, threading.Event] = {}

    @property
    def attribution(self) -> str | None:
        return self._inner.attribution

    @property
    def inner(self) -> Geocoder:
        """The geocoder this one answers for."""
        return self._inner

    def geocode(self, address: str) -> GeocodeResult | None:
        key = " ".join(address.split()).lower()

        while True:
            with self._lock:
                entry = self._known(key)
                if entry is not None:
                    return entry.result
                event = self._inflight.get(key)
                mine = event is None
                if event is None:
                    event = threading.Event()
                    self._inflight[key] = event

            if not mine:
                # Somebody else is asking for this address. Wait for
                # their answer rather than asking the provider again.
                if event.wait(timeout=_WAIT_SECONDS):
                    continue
                # They have gone quiet, which the provider's own
                # timeout should not allow. The answer is worth having
                # anyway.
                return self._inner.geocode(address)

            try:
                result = self._inner.geocode(address)
            except BaseException:
                with self._lock:
                    self._inflight.pop(key, None)
                    event.set()
                raise
            with self._lock:
                self._entries[key] = _Entry(result=result, stored_at=self._clock())
                self._inflight.pop(key, None)
                self._drop_the_oldest()
                # The event is set while the lock is held, so a caller
                # that wakes up finds the answer in the table and does
                # not ask the provider a second time.
                event.set()
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
