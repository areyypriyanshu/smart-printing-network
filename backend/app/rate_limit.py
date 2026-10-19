import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app.errors import RateLimited


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def check(
        self, key: str, limit: int, window_seconds: float, now: float | None = None
    ) -> float | None:
        current = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            cutoff = current - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return bucket[0] + window_seconds - current
            bucket.append(current)
            return None


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
