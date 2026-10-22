"""One call at a time.

The public OpenStreetMap geocoder asks for no more than one request a
second, and it asks for it from the whole application rather than from
one customer. So the limit lives on the process, not on a user, and it
is enforced here rather than in the route.

Waiting is done under the lock on purpose: two customers asking at the
same moment must not both go out and then come back and go out again.
They take turns, and the second one waits.
"""

import threading
import time
from collections.abc import Callable


class Throttle:
    """Allows one call, then waits until the next one is allowed."""

    def __init__(
        self,
        *,
        min_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_call: float | None = None

    def wait(self) -> None:
        """Wait until a call is allowed to go out."""
        with self._lock:
            now = self._clock()
            if self._last_call is not None:
                gap = now - self._last_call
                if gap < self._min_interval:
                    self._sleep(self._min_interval - gap)
            self._last_call = self._clock()

    @property
    def min_interval_seconds(self) -> float:
        return self._min_interval
