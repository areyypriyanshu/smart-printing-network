from datetime import UTC, datetime

import pytest
from app.models import Order, OrderEvent, Shop, Upload
from app.services import backtest_service, history_seed_service
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import create_full_rate_table, create_reserved_order, create_shop, create_user

NOW = datetime(2026, 2, 1, tzinfo=UTC)


def _shop(session: Session):
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    return shop


def _history_shape(session: Session) -> list[tuple[object, ...]]:
    rows = session.execute(
        select(
            Order.idempotency_key,
            Order.page_count,
            Order.copies,
            OrderEvent.to_status,
            OrderEvent.at,
        )
        .join(OrderEvent, OrderEvent.order_id == Order.id)
        .join(Upload, Upload.id == Order.upload_id)
        .where(Order.idempotency_key.like("simulated-history-%"))
        .where(Upload.file_key.like("simulated-history/%"))
        .order_by(Order.idempotency_key, OrderEvent.at, OrderEvent.id)
    ).all()
    return [tuple(row) for row in rows]


def test_history_seed_is_deterministic_and_rerun_replaces_only_its_dataset(
    db_session: Session,
) -> None:
    _shop(db_session)

    first_count = history_seed_service.seed_history(db_session, orders_per_shop=3, seed=11, now=NOW)
    first_shape = _history_shape(db_session)
    unrelated = create_reserved_order(
        db_session,
        customer=create_user(db_session, email="unrelated@example.com"),
        shop=db_session.scalar(select(Shop)),
    )
    # A customer may choose this key too; it must not make their order part of
    # the simulated dataset or allow the next run to delete it.
    unrelated.idempotency_key = f"{history_seed_service.SIMULATED_HISTORY_PREFIX}customer-collision"
    db_session.commit()
    second_count = history_seed_service.seed_history(
        db_session, orders_per_shop=3, seed=11, now=NOW
    )
    second_shape = _history_shape(db_session)

    assert first_count == second_count == 3
    assert first_shape == second_shape
    assert db_session.get(Order, unrelated.id) is not None
    report_orders = backtest_service.load_history(
        db_session,
        idempotency_prefix=history_seed_service.SIMULATED_HISTORY_PREFIX,
        storage_key_prefix=history_seed_service.SIMULATED_FILE_PREFIX,
    )
    assert unrelated.id not in {order.id for order in report_orders}
    assert len(report_orders) == 3
    orders = list(
        db_session.scalars(
            select(Order)
            .join(Upload, Upload.id == Order.upload_id)
            .where(Order.idempotency_key.like("simulated-history-%"))
            .where(Upload.file_key.like("simulated-history/%"))
        )
    )
    assert len(orders) == 3
    assert all(order.status == "COLLECTED" for order in orders)
    for order in orders:
        events = list(
            db_session.scalars(
                select(OrderEvent)
                .where(OrderEvent.order_id == order.id)
                .order_by(OrderEvent.at, OrderEvent.id)
            )
        )
        assert [event.to_status for event in events] == [
            "RESERVED",
            "ACCEPTED",
            "PRINTING",
            "READY",
            "COLLECTED",
        ]
        assert all(
            later.at > earlier.at for earlier, later in zip(events, events[1:], strict=False)
        )
        upload = db_session.get(Upload, order.upload_id)
        assert upload is not None
        assert upload.original_filename == "simulated-history.pdf"
        assert upload.file_deleted_at is not None


def test_history_seed_refuses_production(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.history_seed_service.get_settings",
        lambda: type("Settings", (), {"env": "production", "cash_at_store_enabled": True})(),
    )

    with pytest.raises(SystemExit):
        history_seed_service.seed_history(db_session, now=NOW)

    assert list(db_session.scalars(select(Order))) == []
