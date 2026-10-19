from app.rate_limit import RateLimiter


def test_allows_up_to_limit_then_blocks() -> None:
    limiter = RateLimiter()

    for _ in range(3):
        assert limiter.check("key", 3, 60, now=0.0) is None

    assert limiter.check("key", 3, 60, now=0.0) == 60.0


def test_window_slides_and_refills() -> None:
    limiter = RateLimiter()
    limiter.check("key", 1, 10, now=0.0)

    assert limiter.check("key", 1, 10, now=9.9) is not None
    assert limiter.check("key", 1, 10, now=10.1) is None


def test_keys_are_isolated() -> None:
    limiter = RateLimiter()
    limiter.check("first", 1, 10, now=0.0)

    assert limiter.check("second", 1, 10, now=0.0) is None


def test_is_blocked_does_not_consume_an_attempt() -> None:
    limiter = RateLimiter()
    limiter.record("key", now=0.0)

    assert limiter.is_blocked("key", 1, 10, now=0.0) is not None
    assert limiter.is_blocked("other", 1, 10, now=0.0) is None


def test_record_counts_attempts_towards_the_limit() -> None:
    limiter = RateLimiter()

    for _ in range(5):
        limiter.record("key", now=0.0)

    assert limiter.is_blocked("key", 5, 600, now=0.0) is not None
    assert limiter.is_blocked("key", 6, 600, now=0.0) is None


def test_the_window_slides_for_recorded_attempts() -> None:
    limiter = RateLimiter()
    limiter.record("key", now=0.0)

    assert limiter.is_blocked("key", 1, 10, now=9.9) is not None
    assert limiter.is_blocked("key", 1, 10, now=10.1) is None
