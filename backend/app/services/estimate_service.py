"""Shop queue-wait estimates from order events and current unfinished work."""

import logging
import uuid
from datetime import datetime

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.estimates import (
    ALGORITHM_VERSION,
    QUEUE_STATUSES,
    RECENT_SAMPLE_LIMIT,
    SpeedProfile,
    estimate_from_work,
    profile_from_quartiles,
)
from app.errors import NotFound
from app.models import Order, Shop
from app.schemas.shop import WaitEstimateResponse

logger = logging.getLogger(__name__)

# Invalid durations are removed before recency is assigned, so a corrupt row
# cannot push a valid sample out of the recent fifty. The cutoff is strict:
# backtests must not learn from a completion at or after their prediction time.
_RECENT_SPEEDS = text(
    """
    WITH recent AS (
        SELECT
            d.shop_id,
            d.print_minutes,
            d.print_units,
            ROW_NUMBER() OVER (
                PARTITION BY d.shop_id
                ORDER BY d.completed_at DESC, d.ready_event_id DESC
            ) AS recency
        FROM order_print_durations d
        WHERE d.shop_id IN :shop_ids
          AND d.print_minutes > 0
          AND d.print_units > 0
          AND (CAST(:as_of AS timestamptz) IS NULL OR d.completed_at < CAST(:as_of AS timestamptz))
    )
    SELECT
        shop_id,
        percentile_cont(0.25) WITHIN GROUP (
            ORDER BY print_minutes / print_units
        ) AS p25,
        percentile_cont(0.50) WITHIN GROUP (
            ORDER BY print_minutes / print_units
        ) AS median,
        percentile_cont(0.75) WITHIN GROUP (
            ORDER BY print_minutes / print_units
        ) AS p75,
        count(*) AS sample_count
    FROM recent
    WHERE recency <= :recent_limit
    GROUP BY shop_id
    """
).bindparams(
    bindparam("shop_ids", expanding=True),
    bindparam("as_of", required=False),
    bindparam("recent_limit", RECENT_SAMPLE_LIMIT),
)


def get_wait_estimate(session: Session, *, shop_id: uuid.UUID) -> WaitEstimateResponse:
    """Estimate one publicly visible shop, or conceal it with a 404.

    The batch read performs the only visibility check, so a suspension between
    two reads cannot turn into a KeyError and a 500.
    """
    estimate = estimates_for_shops(session, [shop_id]).get(shop_id)
    if estimate is None:
        raise NotFound("Shop not found")
    return estimate


def estimates_for_shops(
    session: Session,
    shop_ids: list[uuid.UUID],
) -> dict[uuid.UUID, WaitEstimateResponse]:
    """Batch the two aggregate reads used by every public shop list.

    Verified shops remain readable when they stop accepting new orders, just
    as they are on the existing shop-detail route. This matters to a customer
    looking at an existing order. Public list endpoints independently retain
    their accepting-only filter.
    """
    ids = list(dict.fromkeys(shop_ids))
    if not ids:
        return {}
    visible_ids = list(
        session.scalars(select(Shop.id).where(Shop.id.in_(ids), Shop.is_verified.is_(True)))
    )
    if not visible_ids:
        return {}

    queue_totals = {
        shop_id: (order_count, int(unit_count or 0))
        for shop_id, order_count, unit_count in session.execute(
            select(
                Order.shop_id,
                func.count(Order.id),
                func.sum(Order.page_count * Order.copies),
            )
            .where(Order.shop_id.in_(visible_ids), Order.status.in_(QUEUE_STATUSES))
            .group_by(Order.shop_id)
        )
    }
    profiles = speed_profiles_for_shops(session, visible_ids)
    return {
        shop_id: _response(
            shop_id,
            queue_totals.get(shop_id, (0, 0)),
            profiles.get(
                shop_id, profile_from_quartiles(sample_count=0, p25=None, median=None, p75=None)
            ),
        )
        for shop_id in visible_ids
    }


def estimates_for_shops_or_empty(
    session: Session, shop_ids: list[uuid.UUID]
) -> dict[uuid.UUID, WaitEstimateResponse]:
    """Keep an optional statistic from taking down the core shop discovery flow.

    The savepoint contains the rollback to the failed statistics reads; it does
    not roll back the request's earlier reads or any outer test transaction.
    The single-shop endpoint deliberately does not use this fallback.
    """
    try:
        with session.begin_nested():
            return estimates_for_shops(session, shop_ids)
    except SQLAlchemyError:
        logger.warning("wait estimates are unavailable for a shop list", exc_info=True)
        return {}


def speed_profiles_for_shops(
    session: Session, shop_ids: list[uuid.UUID], *, as_of: datetime | None = None
) -> dict[uuid.UUID, SpeedProfile]:
    """Read recent speed profiles, optionally before a replay cutoff.

    This statistics-only cutoff is public for evaluation and its tests. It is
    deliberately not an argument to the live estimate: historical queue state
    must be reconstructed from events, not read from the current orders table.
    """
    _check_cutoff(as_of)
    if not shop_ids:
        return {}
    profiles: dict[uuid.UUID, SpeedProfile] = {}
    for row in session.execute(
        _RECENT_SPEEDS,
        {"shop_ids": shop_ids, "as_of": as_of, "recent_limit": RECENT_SAMPLE_LIMIT},
    ).mappings():
        profiles[row["shop_id"]] = profile_from_quartiles(
            sample_count=int(row["sample_count"]),
            p25=_float_or_none(row["p25"]),
            median=_float_or_none(row["median"]),
            p75=_float_or_none(row["p75"]),
        )
    return profiles


def _response(
    shop_id: uuid.UUID, totals: tuple[int, int], profile: SpeedProfile
) -> WaitEstimateResponse:
    queue_orders, queue_units = totals
    estimate = estimate_from_work(
        queue_orders=queue_orders, queue_units=queue_units, profile=profile
    )
    return WaitEstimateResponse(
        shop_id=shop_id,
        minimum_minutes=estimate.minimum_minutes,
        median_minutes=estimate.median_minutes,
        maximum_minutes=estimate.maximum_minutes,
        sample_count=estimate.sample_count,
        rough=estimate.rough,
        algorithm_version=ALGORITHM_VERSION,
    )


def _float_or_none(value: object) -> float | None:
    # PostgreSQL may return either a float or Decimal for this expression.
    return None if value is None else float(str(value))


def _check_cutoff(as_of: datetime | None) -> None:
    if as_of is not None and (as_of.tzinfo is None or as_of.utcoffset() is None):
        raise ValueError("as_of must be timezone-aware")
