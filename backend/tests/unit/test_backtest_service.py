import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.services.backtest_service import (
    HistoryEvent,
    HistoryOrder,
    build_report,
    replay_history,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)
SHOP = uuid.UUID("aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
OTHER_SHOP = uuid.UUID("bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb")


def _order(
    number: int,
    schedule: list[tuple[str, int]],
    *,
    units: int = 2,
    shop_id: uuid.UUID = SHOP,
) -> HistoryOrder:
    return HistoryOrder(
        id=uuid.UUID(int=number),
        shop_id=shop_id,
        shop_name="Test Shop" if shop_id == SHOP else "Other Shop",
        print_units=units,
        events=tuple(
            HistoryEvent(id=event_id, at=BASE + timedelta(minutes=minutes), to_status=status)
            for event_id, (status, minutes) in enumerate(schedule, start=number * 100)
        ),
    )


def _three_orders() -> list[HistoryOrder]:
    return [
        _order(1, [("RESERVED", 0), ("PRINTING", 10), ("READY", 20)]),
        _order(2, [("RESERVED", 11), ("PRINTING", 21), ("READY", 31)]),
        _order(3, [("RESERVED", 22), ("PRINTING", 32), ("READY", 42)]),
    ]


def test_walk_forward_has_hand_computable_predictions_and_baseline() -> None:
    result = replay_history(_three_orders())

    # Order 1 has no earlier actual, so it is warm-up. At order 2, order 1
    # is still printing: 2 units x the 0.5 default = 1 minute, while the
    # baseline is order 1's actual 10 minutes. At order 3, order 1's speed
    # (10 / 2 = 5) is available, order 2 is printing, and both actuals are
    # known. There is only one speed sample, so the <10 fallback still gives
    # 2 units x 0.5 = 1 minute; the baseline is 10.
    assert result.skipped_warmup == 1
    assert len(result.rows) == 2
    second, third = result.rows
    assert second.predicted_minutes == pytest.approx(1)
    assert second.baseline_minutes == pytest.approx(10)
    assert second.actual_minutes == pytest.approx(10)
    assert third.predicted_minutes == pytest.approx(1)
    assert third.baseline_minutes == pytest.approx(10)
    assert third.actual_minutes == pytest.approx(10)


def test_replay_uses_shop_speed_once_ten_samples_exist() -> None:
    orders = [
        _order(
            number,
            [("RESERVED", number * 10), ("PRINTING", number * 10 + 2), ("READY", number * 10 + 4)],
        )
        for number in range(10)
    ]
    active = _order(11, [("RESERVED", 95), ("PRINTING", 96), ("READY", 116)])
    target = _order(12, [("RESERVED", 100), ("PRINTING", 110), ("READY", 120)])

    result = replay_history([*orders, active, target])
    target_row = result.rows[-1]

    assert target_row.predicted_minutes == pytest.approx(2)
    assert target_row.baseline_minutes == pytest.approx(21 / 11)
    assert target_row.rough is False


def test_future_outlier_changes_neither_earlier_estimate_nor_baseline() -> None:
    original = replay_history(_three_orders())
    with_outlier = replay_history(
        [
            *_three_orders(),
            _order(4, [("RESERVED", 50), ("PRINTING", 1050), ("READY", 1051)]),
        ]
    )

    assert with_outlier.rows[:2] == original.rows


def test_one_shops_work_never_inflates_another_shops_estimate() -> None:
    baseline = _order(1, [("RESERVED", -20), ("PRINTING", -10), ("READY", -5)])
    shop_a_work = _order(2, [("RESERVED", 0), ("PRINTING", 30), ("READY", 40)])
    shop_b_work = _order(
        3,
        [("RESERVED", 1), ("PRINTING", 31), ("READY", 61)],
        units=100,
        shop_id=OTHER_SHOP,
    )
    shop_a_target = _order(4, [("RESERVED", 2), ("PRINTING", 12), ("READY", 22)])

    result = replay_history([baseline, shop_a_work, shop_b_work, shop_a_target])
    by_order = {row.order_id: row for row in result.rows}

    # At minute 1, shop B has no work of its own, so its estimate is zero.
    # At minute 2, shop A has only its own two units, not B's 100 units.
    # Both use the <10 fallback and the already-known 10-minute global baseline.
    assert by_order[shop_b_work.id].predicted_minutes == 0
    assert by_order[shop_a_target.id].predicted_minutes == pytest.approx(1)
    assert by_order[shop_a_target.id].baseline_minutes == pytest.approx(10)


def test_cancelled_work_leaves_the_reconstructed_queue() -> None:
    first = _order(1, [("RESERVED", -20), ("PRINTING", -10), ("READY", -5)])
    cancelled = _order(2, [("RESERVED", 0), ("CANCELLED", 5)], units=100)
    target = _order(3, [("RESERVED", 6), ("PRINTING", 16), ("READY", 26)])

    result = replay_history([first, cancelled, target])

    assert len(result.rows) == 1
    assert result.rows[0].predicted_minutes == 0
    assert result.rows[0].baseline_minutes == pytest.approx(10)


def test_unpaid_order_is_incomplete_not_a_zero_error_or_a_win() -> None:
    unpaid = _order(1, [("PENDING_PAYMENT", 0), ("EXPIRED", 15)])

    result = replay_history([unpaid])
    report = build_report(result, data_source="real")

    assert result.orders_read == 1
    assert result.rows == ()
    assert result.skipped_warmup == 0
    assert result.skipped_incomplete == 1
    assert report["overall"]["rule_mae_minutes"] is None
    assert report["overall"]["baseline_mae_minutes"] is None
    assert report["overall"]["rule_beats_baseline"] is None


def test_report_uses_null_not_zero_or_a_win_when_there_is_no_evidence() -> None:
    result = replay_history([])

    report = build_report(result, data_source="simulated")

    assert report["simulated"] is True
    assert report["overall"] == {
        "n": 0,
        "rule_mae_minutes": None,
        "baseline_mae_minutes": None,
        "rule_beats_baseline": None,
        "rough_predictions": 0,
    }
    assert report["shops"] == []


def test_report_records_a_loss_honestly() -> None:
    result = replay_history(_three_orders())
    report = build_report(result, data_source="simulated")
    overall = report["overall"]

    assert overall["rule_mae_minutes"] == pytest.approx(9.0)
    assert overall["baseline_mae_minutes"] == pytest.approx(0)
    assert overall["rule_beats_baseline"] is False
    assert result.orders_read == (
        len(result.rows) + result.skipped_warmup + result.skipped_incomplete
    )
