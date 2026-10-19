import math
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable

from fastapi import Depends, Request

from app.deps import get_current_user
from app.errors import RateLimited
from app.models import User

PICKUP_MAX_ATTEMPTS = 5
PICKUP_WINDOW_SECONDS = 600.0

#: How many times wider the limit for a whole address is than the limit
#: for one account. The address limit only has to stop a machine
#: spraying many accounts, so it can be generous.
ADDRESS_LIMIT_FACTOR = 4


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def check(
        self, key: str, limit: int, window_seconds: float, now: float | None = None
    ) -> float | None:
        """Allow one use of `key`, or report how long to wait if it is used up.

        Records the attempt when it is allowed. Use `is_blocked` and
        `record` separately when an attempt should only be counted on
        failure.
        """
        current = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._prune(key, current, window_seconds)
            if len(bucket) >= limit:
                return bucket[0] + window_seconds - current
            bucket.append(current)
            return None

    def is_blocked(
        self, key: str, limit: int, window_seconds: float, now: float | None = None
    ) -> float | None:
        """Report whether `key` is used up, without recording an attempt."""
        current = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._prune(key, current, window_seconds)
            if len(bucket) >= limit:
                return bucket[0] + window_seconds - current
            return None

    def record(self, key: str, now: float | None = None) -> None:
        """Record one attempt against `key` without enforcing a limit."""
        current = time.monotonic() if now is None else now
        with self._lock:
            self._hits.setdefault(key, deque()).append(current)

    def _prune(self, key: str, current: float, window_seconds: float) -> deque[float]:
        bucket = self._hits.setdefault(key, deque())
        cutoff = current - window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        return bucket


def rate_limit(times: int, seconds: float, scope: str) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        limiter: RateLimiter = request.app.state.rate_limiter
        client = request.client.host if request.client else "unknown"
        retry_after = limiter.check(f"{scope}:{client}", times, seconds)
        if retry_after is not None:
            raise RateLimited(
                "Too many requests, try again shortly",
                headers={"Retry-After": str(math.ceil(retry_after))},
            )

    return dependency


def account_rate_limit(
    times: int, seconds: float, scope: str, account_from: Callable[[Request], str]
) -> Callable[[Request], None]:
    """Limit an action per account, with a wider limit for the whole address.

    A login attempt is counted twice: once against the account being
    tried, and once against the address it came from. Guessing one
    password over and over is stopped by the account limit, and spraying
    many passwords at many accounts from one machine is stopped by the
    address limit.

    The two are separate because a college puts every student behind one
    address. A limit of ten logins a minute for the whole campus would
    lock out a class, while ten guesses a minute against one account is
    what actually stops a brute force.
    """

    def dependency(request: Request) -> None:
        limiter: RateLimiter = request.app.state.rate_limiter
        client = request.client.host if request.client else "unknown"
        account = account_from(request)
        for key, limit in (
            (f"{scope}:account:{account}", times),
            (f"{scope}:address:{client}", times * ADDRESS_LIMIT_FACTOR),
        ):
            retry_after = limiter.check(key, limit, seconds)
            if retry_after is not None:
                raise RateLimited(
                    "Too many requests, try again shortly",
                    headers={"Retry-After": str(math.ceil(retry_after))},
                )

    return dependency


def user_rate_limit(times: int, seconds: float, scope: str) -> Callable[..., None]:
    def dependency(request: Request, user: User = Depends(get_current_user)) -> None:
        limiter: RateLimiter = request.app.state.rate_limiter
        retry_after = limiter.check(f"{scope}:{user.id}", times, seconds)
        if retry_after is not None:
            raise RateLimited(
                "Too many requests, try again shortly",
                headers={"Retry-After": str(math.ceil(retry_after))},
            )

    return dependency


def get_rate_limiter(request: Request) -> RateLimiter:
    """The per-process limiter instance, one per application."""
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def pickup_attempt_key(order_id: uuid.UUID) -> str:
    return f"pickup:{order_id}"


def enforce_pickup_attempt_limit(limiter: RateLimiter, order_id: uuid.UUID) -> None:
    """Raise when too many pickup codes have been tried for this order.

    Invariant I14: at most 5 attempts per order per 10 minutes. The counter
    is per order rather than per vendor so one busy shop cannot lock a
    colleague out of a different order.
    """
    retry_after = limiter.is_blocked(
        pickup_attempt_key(order_id), PICKUP_MAX_ATTEMPTS, PICKUP_WINDOW_SECONDS
    )
    if retry_after is not None:
        raise RateLimited(
            "Too many pickup code attempts. Try again in a few minutes.",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )


def record_pickup_attempt(limiter: RateLimiter, order_id: uuid.UUID) -> None:
    """Count one failed pickup code attempt against the order."""
    limiter.record(pickup_attempt_key(order_id))
