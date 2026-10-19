from app.domain.refunds import (
    MAX_BACKOFF_MINUTES,
    refund_backoff_minutes,
    refund_backoff_seconds,
)
from hypothesis import given
from hypothesis import strategies as st


def test_the_first_retry_waits_one_minute() -> None:
    assert refund_backoff_minutes(1) == 1


def test_the_backoff_doubles() -> None:
    assert [refund_backoff_minutes(n) for n in (1, 2, 3, 4, 5)] == [1, 2, 4, 8, 16]


def test_the_backoff_is_capped_at_an_hour() -> None:
    assert refund_backoff_minutes(10) == MAX_BACKOFF_MINUTES
    assert refund_backoff_minutes(100) == MAX_BACKOFF_MINUTES


def test_a_negative_attempt_count_still_waits_a_minute() -> None:
    assert refund_backoff_minutes(0) == 1
    assert refund_backoff_minutes(-5) == 1


def test_seconds_match_minutes() -> None:
    assert refund_backoff_seconds(1) == 60
    assert refund_backoff_seconds(3) == 240


@given(st.integers(min_value=0, max_value=50))
def test_the_backoff_never_leaves_the_allowed_range(attempts: int) -> None:
    minutes = refund_backoff_minutes(attempts)
    assert 1 <= minutes <= MAX_BACKOFF_MINUTES
