"""Pure rules for shop queue-wait estimates.

The estimate answers one deliberately narrow question: how long a newly
arriving order might wait before the shop starts printing it. It is not a
promise about when that order will be ready. The backtest uses the same
measurand: the time from entering the shop queue to the PRINTING event.

A speed sample is minutes per print unit (pages multiplied by copies), measured
from PRINTING to READY. Consequently the sample already contains the shop's
ordinary handling time; adding a second per-order overhead would double count
it. Only unfinished queue work is included. A currently printing order is
counted at its full size because the system records no page-level progress.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite

MIN_SAMPLES = 10
RECENT_SAMPLE_LIMIT = 50
ALGORITHM_VERSION = "1"

# These are deliberately boring planning defaults, not learned parameters.
# They are used only when a shop has too little history and every response
# marks that situation as rough. The values are minutes per page-copy.
DEFAULT_P25_MINUTES_PER_UNIT = 0.35
DEFAULT_MEDIAN_MINUTES_PER_UNIT = 0.50
DEFAULT_P75_MINUTES_PER_UNIT = 0.75

# READY is intentionally absent: its printing work is finished. PENDING_PAYMENT
# is absent too: it has not entered the shop's queue. RESERVED is included so
# cash orders wait in exactly the same queue as online orders.
QUEUE_STATUSES = frozenset({"PAID", "RESERVED", "ACCEPTED", "PRINTING"})


@dataclass(frozen=True)
class SpeedProfile:
    """The recent speed distribution for one shop."""

    p25: float
    median: float
    p75: float
    sample_count: int
    rough: bool


@dataclass(frozen=True)
class Estimate:
    """A queue-wait range in minutes, with the evidence used to make it."""

    minimum_minutes: float
    median_minutes: float
    maximum_minutes: float
    sample_count: int
    rough: bool
    queue_orders: int
    queue_units: int


def percentile(values: Iterable[float], fraction: float) -> float:
    """Return a linearly interpolated percentile, like PostgreSQL's cont variant."""
    if not 0 <= fraction <= 1:
        raise ValueError("percentile fraction must be between zero and one")
    ordered = sorted(values)
    if not ordered:
        raise ValueError("a percentile needs at least one value")
    if any(not isfinite(value) or value <= 0 for value in ordered):
        raise ValueError("speed samples must be finite and positive")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def profile_from_quartiles(
    *,
    sample_count: int,
    p25: float | None,
    median: float | None,
    p75: float | None,
) -> SpeedProfile:
    """Use shop quartiles at ten samples, or the documented fallback below it."""
    if sample_count < 0:
        raise ValueError("sample count cannot be negative")
    if sample_count < MIN_SAMPLES:
        return SpeedProfile(
            p25=DEFAULT_P25_MINUTES_PER_UNIT,
            median=DEFAULT_MEDIAN_MINUTES_PER_UNIT,
            p75=DEFAULT_P75_MINUTES_PER_UNIT,
            sample_count=sample_count,
            rough=True,
        )
    if p25 is None or median is None or p75 is None:
        raise ValueError("a full speed profile needs all three quartiles")
    values = (p25, median, p75)
    if any(not isfinite(value) or value <= 0 for value in values):
        raise ValueError("speed profile must be finite and positive")
    if not p25 <= median <= p75:
        raise ValueError("speed profile quartiles are out of order")
    return SpeedProfile(p25, median, p75, sample_count, False)


def speed_profile(samples: Iterable[float]) -> SpeedProfile:
    """Build a profile, falling back to defaults until ten samples exist.

    The actual number of valid samples is retained even when the fallback is
    used, so the caller can explain why the estimate is rough.
    """
    values = list(samples)
    if any(not isfinite(value) or value <= 0 for value in values):
        raise ValueError("speed samples must be finite and positive")
    return profile_from_quartiles(
        sample_count=len(values),
        p25=percentile(values, 0.25) if len(values) >= MIN_SAMPLES else None,
        median=percentile(values, 0.50) if len(values) >= MIN_SAMPLES else None,
        p75=percentile(values, 0.75) if len(values) >= MIN_SAMPLES else None,
    )


def estimate_from_work(*, queue_orders: int, queue_units: int, profile: SpeedProfile) -> Estimate:
    """Apply a speed profile to an aggregate of unfinished queue work."""
    if (
        isinstance(queue_orders, bool)
        or not isinstance(queue_orders, int)
        or queue_orders < 0
        or isinstance(queue_units, bool)
        or not isinstance(queue_units, int)
        or queue_units < 0
    ):
        raise ValueError("queue totals must be non-negative integers")
    if (queue_orders == 0) != (queue_units == 0):
        raise ValueError("an empty queue has no orders and no units")
    if any(
        not isfinite(speed) or speed <= 0 for speed in (profile.p25, profile.median, profile.p75)
    ):
        raise ValueError("speed profile must be finite and positive")
    if not profile.p25 <= profile.median <= profile.p75:
        raise ValueError("speed profile quartiles are out of order")
    if profile.sample_count < 0:
        raise ValueError("sample count cannot be negative")
    if queue_units == 0:
        return Estimate(0.0, 0.0, 0.0, profile.sample_count, profile.rough, 0, 0)
    return Estimate(
        minimum_minutes=queue_units * profile.p25,
        median_minutes=queue_units * profile.median,
        maximum_minutes=queue_units * profile.p75,
        sample_count=profile.sample_count,
        rough=profile.rough,
        queue_orders=queue_orders,
        queue_units=queue_units,
    )


def estimate_from_profile(queue_units: Iterable[int], profile: SpeedProfile) -> Estimate:
    """Apply a speed profile to the unfinished units in a shop's queue."""
    units = list(queue_units)
    if any(isinstance(unit, bool) or not isinstance(unit, int) or unit <= 0 for unit in units):
        raise ValueError("queue print units must be positive integers")
    return estimate_from_work(queue_orders=len(units), queue_units=sum(units), profile=profile)


def estimate_queue_wait(queue_units: Iterable[int], speed_samples: Iterable[float]) -> Estimate:
    """Build a shop speed profile and estimate the current queue wait."""
    return estimate_from_profile(queue_units, speed_profile(speed_samples))
