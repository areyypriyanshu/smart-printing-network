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
