"""Walk-forward replay of queue-wait estimates against order events."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.estimates import ALGORITHM_VERSION, RECENT_SAMPLE_LIMIT, estimate_queue_wait
from app.models import Order, OrderEvent, Shop, Upload


@dataclass(frozen=True)
class HistoryEvent:
    id: int
    at: datetime
    to_status: str


@dataclass(frozen=True)
class HistoryOrder:
    id: uuid.UUID
    shop_id: uuid.UUID
    shop_name: str
    print_units: int
    events: tuple[HistoryEvent, ...]


@dataclass(frozen=True)
class BacktestRow:
    order_id: uuid.UUID
    shop_id: uuid.UUID
    predicted_minutes: float
    baseline_minutes: float
    actual_minutes: float
    rough: bool


@dataclass(frozen=True)
class BacktestResult:
    rows: tuple[BacktestRow, ...]
    skipped_warmup: int
    skipped_incomplete: int
    orders_read: int
    shop_names: dict[uuid.UUID, str]


@dataclass(frozen=True)
class _Pending:
    entry_at: datetime
    predicted_minutes: float
    baseline_minutes: float | None
    rough: bool


def load_history(
    session: Session, *, idempotency_prefix: str = "", storage_key_prefix: str = ""
) -> list[HistoryOrder]:
    """Read orders and their real event trails, optionally only one labelled dataset.

    A simulated report must also be scoped by server-generated storage keys:
    customers may choose any idempotency key, including a simulated-looking one.
    """
    statement = (
        select(Order, Shop.name)
        .join(Shop, Shop.id == Order.shop_id)
        .join(Upload, Upload.id == Order.upload_id)
        .order_by(Order.created_at, Order.id)
    )
    if idempotency_prefix:
        statement = statement.where(Order.idempotency_key.like(f"{idempotency_prefix}%"))
    if storage_key_prefix:
        statement = statement.where(Upload.file_key.like(f"{storage_key_prefix}%"))
    order_rows = list(session.execute(statement).all())
    order_ids = [order.id for order, _name in order_rows]
    events_by_order: dict[uuid.UUID, list[HistoryEvent]] = defaultdict(list)
    if order_ids:
        for event in session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id.in_(order_ids))
            .order_by(OrderEvent.at, OrderEvent.id)
        ):
            events_by_order[event.order_id].append(
                HistoryEvent(id=event.id, at=event.at, to_status=event.to_status)
            )
    return [
        HistoryOrder(
            id=order.id,
            shop_id=order.shop_id,
            shop_name=name,
            print_units=order.page_count * order.copies,
            events=tuple(events_by_order[order.id]),
        )
        for order, name in order_rows
    ]


def replay_history(orders: list[HistoryOrder]) -> BacktestResult:
    """Replay events in order, never reading the future at a prediction point.

    The actual wait becomes known at PRINTING, so only those earlier PRINTING
    events feed the expanding global-average baseline. A speed sample becomes
    available at READY. Current PRINTING work counts at full size, matching the
    live estimator; READY and terminal orders leave the queue.
    """
    by_id = {order.id: order for order in orders}
    timeline = sorted(
        (
            (event.at, event.id, order.id, event.to_status)
            for order in orders
            for event in order.events
        ),
        key=lambda item: (item[0], item[1], str(item[2])),
    )
    queues: dict[uuid.UUID, dict[uuid.UUID, int]] = defaultdict(dict)
    pending: dict[uuid.UUID, _Pending] = {}
    entered: set[uuid.UUID] = set()
    printing_at: dict[uuid.UUID, datetime] = {}
    speed_samples: dict[uuid.UUID, list[float]] = defaultdict(list)
    known_actual_waits: list[float] = []
    rows: list[BacktestRow] = []
    skipped_warmup = 0

    for at, _event_id, order_id, status in timeline:
        order = by_id[order_id]
        if status in {"PAID", "RESERVED"} and order_id not in entered:
            samples = speed_samples[order.shop_id][-RECENT_SAMPLE_LIMIT:]
            estimate = estimate_queue_wait(queues[order.shop_id].values(), samples)
            baseline = (
                sum(known_actual_waits) / len(known_actual_waits) if known_actual_waits else None
            )
            pending[order_id] = _Pending(at, estimate.median_minutes, baseline, estimate.rough)
            entered.add(order_id)
            queues[order.shop_id][order_id] = order.print_units
            continue

        if status == "PRINTING":
            printing_at[order_id] = at
            prediction = pending.pop(order_id, None)
            if prediction is not None:
                actual = (at - prediction.entry_at).total_seconds() / 60.0
                if actual >= 0:
                    if prediction.baseline_minutes is None:
                        skipped_warmup += 1
                    else:
                        rows.append(
                            BacktestRow(
                                order_id=order_id,
                                shop_id=order.shop_id,
                                predicted_minutes=prediction.predicted_minutes,
                                baseline_minutes=prediction.baseline_minutes,
                                actual_minutes=actual,
                                rough=prediction.rough,
                            )
                        )
                    # This actual is observable now and can inform later entries.
                    known_actual_waits.append(actual)
            continue

        if status == "READY":
            started = printing_at.get(order_id)
            if started is not None:
                duration = (at - started).total_seconds() / 60.0
                if duration > 0 and order.print_units > 0:
                    speed_samples[order.shop_id].append(duration / order.print_units)
            queues[order.shop_id].pop(order_id, None)
            continue

        if status in {"REJECTED", "CANCELLED", "EXPIRED", "COLLECTED"}:
            queues[order.shop_id].pop(order_id, None)
            if order_id in pending and status != "COLLECTED":
                pending.pop(order_id, None)

    # Every unscored order is incomplete for evaluation, not only an order that
    # entered the queue. This includes unpaid/expired orders and invalid or
    # missing target timestamps, and makes the report's accounting exact.
    skipped_incomplete = len(orders) - len(rows) - skipped_warmup
    return BacktestResult(
        rows=tuple(rows),
        skipped_warmup=skipped_warmup,
        skipped_incomplete=skipped_incomplete,
        orders_read=len(orders),
        shop_names={order.shop_id: order.shop_name for order in orders},
    )


def build_report(result: BacktestResult, *, data_source: str) -> dict[str, object]:
    """Aggregate only: no customer, filename, raw event or per-order data."""
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "data_source": data_source,
        "simulated": data_source == "simulated",
        "target": "minutes from queue entry (PAID or RESERVED) to first PRINTING",
        "baseline": "expanding global mean of actual waits already known at prediction time",
        "range_note": "p25-p75 is a heuristic speed range, not a confidence interval",
        "orders_read": result.orders_read,
        "evaluated_orders": len(result.rows),
        "skipped_warmup": result.skipped_warmup,
        "skipped_incomplete": result.skipped_incomplete,
        "overall": _metrics(result.rows),
        "shops": [
            {
                "shop_id": str(shop_id),
                "shop_name": shop_name,
                **_metrics([row for row in result.rows if row.shop_id == shop_id]),
            }
            for shop_id, shop_name in sorted(
                result.shop_names.items(), key=lambda item: (item[1], str(item[0]))
            )
        ],
    }


def _metrics(rows: list[BacktestRow] | tuple[BacktestRow, ...]) -> dict[str, object]:
    if not rows:
        return {
            "n": 0,
            "rule_mae_minutes": None,
            "baseline_mae_minutes": None,
            "rule_beats_baseline": None,
            "rough_predictions": 0,
        }
    rule = _mae([abs(row.predicted_minutes - row.actual_minutes) for row in rows])
    baseline = _mae([abs(row.baseline_minutes - row.actual_minutes) for row in rows])
    return {
        "n": len(rows),
        "rule_mae_minutes": round(rule, 4),
        "baseline_mae_minutes": round(baseline, 4),
        "rule_beats_baseline": rule < baseline,
        "rough_predictions": sum(row.rough for row in rows),
    }


def _mae(errors: list[float]) -> float:
    return sum(errors) / len(errors)
