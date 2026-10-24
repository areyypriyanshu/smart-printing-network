from datetime import UTC, datetime

from app.services.backtest_service import build_report, load_history, replay_history
from app.services.history_seed_service import (
    SIMULATED_FILE_PREFIX,
    SIMULATED_HISTORY_PREFIX,
    seed_history,
)
from sqlalchemy.orm import Session
from tests.factories import create_full_rate_table, create_shop, create_user


def test_seeded_history_replays_into_an_aggregate_report(db_session: Session) -> None:
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop)
    seed_history(db_session, orders_per_shop=12, seed=7, now=datetime(2026, 2, 1, tzinfo=UTC))

    result = replay_history(
        load_history(
            db_session,
            idempotency_prefix=SIMULATED_HISTORY_PREFIX,
            storage_key_prefix=SIMULATED_FILE_PREFIX,
        )
    )
    report = build_report(result, data_source="simulated")

    assert report["orders_read"] == 12
    assert report["overall"]["n"] > 0
    assert report["overall"]["rule_mae_minutes"] is not None
    assert report["overall"]["baseline_mae_minutes"] is not None
    assert report["shops"][0]["shop_id"] == str(shop.id)
    assert report["shops"][0]["n"] > 0
    assert "events" not in report
