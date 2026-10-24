import pytest
from app.domain.estimates import (
    DEFAULT_MEDIAN_MINUTES_PER_UNIT,
    MIN_SAMPLES,
    SpeedProfile,
    estimate_from_profile,
    estimate_from_work,
    estimate_queue_wait,
    percentile,
    profile_from_quartiles,
    speed_profile,
)
from hypothesis import given
from hypothesis import strategies as st


def test_empty_queue_is_zero_even_when_history_is_rough() -> None:
    estimate = estimate_queue_wait([], [])

    assert estimate.minimum_minutes == 0
    assert estimate.median_minutes == 0
    assert estimate.maximum_minutes == 0
    assert estimate.queue_orders == 0
    assert estimate.queue_units == 0
    assert estimate.sample_count == 0
    assert estimate.rough is True


def test_one_order_uses_its_units_and_the_speed_quartiles() -> None:
    profile = SpeedProfile(p25=0.25, median=0.5, p75=1.0, sample_count=10, rough=False)

    estimate = estimate_from_profile([4], profile)

    assert estimate.minimum_minutes == 1
    assert estimate.median_minutes == 2
    assert estimate.maximum_minutes == 4
    assert estimate.queue_orders == 1
    assert estimate.queue_units == 4


def test_many_orders_sum_work_instead_of_averaging_it() -> None:
    profile = SpeedProfile(p25=0.25, median=0.5, p75=1.0, sample_count=10, rough=False)

    estimate = estimate_from_profile([2, 3, 5], profile)

    assert estimate.minimum_minutes == 2.5
    assert estimate.median_minutes == 5
    assert estimate.maximum_minutes == 10
    assert estimate.queue_orders == 3
    assert estimate.queue_units == 10


def test_nine_samples_use_the_documented_fallback_and_are_rough() -> None:
    profile = speed_profile([100.0] * (MIN_SAMPLES - 1))

    assert profile.median == DEFAULT_MEDIAN_MINUTES_PER_UNIT
    assert profile.sample_count == 9
    assert profile.rough is True


def test_ten_samples_use_interpolated_shop_quartiles() -> None:
    profile = speed_profile([1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 4.0, 4.0, 5.0, 9.0])

    assert profile.sample_count == 10
    assert profile.rough is False
    assert profile.p25 == pytest.approx(2.25)
    assert profile.median == pytest.approx(3.0)
    assert profile.p75 == pytest.approx(4.0)


def test_percentile_matches_linear_interpolation() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.25) == pytest.approx(1.75)
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.75) == pytest.approx(3.25)


def test_percentile_of_one_value_is_that_value() -> None:
    assert percentile([2.0], 0.75) == 2.0


@pytest.mark.parametrize("fraction", [-0.1, 1.1])
def test_percentile_refuses_an_invalid_fraction(fraction: float) -> None:
    with pytest.raises(ValueError):
        percentile([1.0], fraction)


def test_percentile_refuses_empty_input() -> None:
    with pytest.raises(ValueError):
        percentile([], 0.5)


def test_profile_refuses_a_negative_sample_count() -> None:
    with pytest.raises(ValueError):
        profile_from_quartiles(sample_count=-1, p25=None, median=None, p75=None)


def test_full_profile_refuses_missing_quartiles() -> None:
    with pytest.raises(ValueError):
        profile_from_quartiles(sample_count=10, p25=None, median=0.5, p75=0.75)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_full_profile_refuses_invalid_speeds(bad: float) -> None:
    with pytest.raises(ValueError):
        profile_from_quartiles(sample_count=10, p25=bad, median=0.5, p75=0.75)


def test_full_profile_refuses_out_of_order_quartiles() -> None:
    with pytest.raises(ValueError):
        profile_from_quartiles(sample_count=10, p25=0.8, median=0.5, p75=0.75)


@pytest.mark.parametrize(
    ("orders", "units"),
    [(-1, 1), (1, -1), (True, 1), (1, True), (0, 1), (1, 0)],
)
def test_aggregate_work_refuses_invalid_or_inconsistent_totals(
    orders: object, units: object
) -> None:
    with pytest.raises(ValueError):
        estimate_from_work(queue_orders=orders, queue_units=units, profile=PROFILE)  # type: ignore[arg-type]


def test_aggregate_work_refuses_an_invalid_speed_profile() -> None:
    with pytest.raises(ValueError):
        estimate_from_work(
            queue_orders=1,
            queue_units=1,
            profile=SpeedProfile(0, 0.5, 0.75, 10, False),
        )
    with pytest.raises(ValueError):
        estimate_from_work(
            queue_orders=1,
            queue_units=1,
            profile=SpeedProfile(0.8, 0.5, 0.75, 10, False),
        )
    with pytest.raises(ValueError):
        estimate_from_work(
            queue_orders=1,
            queue_units=1,
            profile=SpeedProfile(0.25, 0.5, 0.75, -1, False),
        )


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_speed_samples_are_refused(bad: float) -> None:
    with pytest.raises(ValueError):
        speed_profile([1.0, bad])


@pytest.mark.parametrize("bad_units", [0, -1, True, 1.5])
def test_invalid_queue_units_are_refused(bad_units: object) -> None:
    profile = SpeedProfile(0.25, 0.5, 0.75, 10, False)
    with pytest.raises(ValueError):
        estimate_from_profile([bad_units], profile)  # type: ignore[list-item]


PROFILE = SpeedProfile(p25=0.25, median=0.5, p75=0.75, sample_count=10, rough=False)


@given(
    units=st.lists(st.integers(min_value=1, max_value=30_000), max_size=20),
    extra=st.integers(min_value=1, max_value=30_000),
)
def test_range_is_ordered_nonnegative_and_monotonic_in_work(units: list[int], extra: int) -> None:
    before = estimate_from_profile(units, PROFILE)
    after = estimate_from_profile([*units, extra], PROFILE)

    assert 0 <= before.minimum_minutes <= before.median_minutes <= before.maximum_minutes
    assert after.minimum_minutes >= before.minimum_minutes
    assert after.median_minutes >= before.median_minutes
    assert after.maximum_minutes >= before.maximum_minutes
    assert after.queue_units == before.queue_units + extra
