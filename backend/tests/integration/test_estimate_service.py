import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models import Order
from app.services import estimate_service
from sqlalchemy import text
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_paid_order,
    create_reserved_order,
    create_shop,
    create_unpaid_order,
    create_user,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _shop(session: Session, email: str = "vendor@example.com"):
    vendor = create_user(session, email=email, role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    return shop


def _completed(
    session: Session,
    customer,
    shop,
    *,
    entry: datetime,
    units: int,
    print_minutes: float,
) -> Order:
    order = create_reserved_order(
        session,
        customer=customer,
        shop=shop,
        reserved_at=entry,
        page_count=units,
    )
    accepted_at = entry + timedelta(minutes=1)
    printing_at = accepted_at + timedelta(minutes=1)
    for status, at in (
        ("ACCEPTED", accepted_at),
        ("PRINTING", printing_at),
        ("READY", printing_at + timedelta(minutes=print_minutes)),
    ):
        order_service_transition(session, order, status, at)
    return order


def order_service_transition(session: Session, order: Order, status: str, at: datetime) -> None:
    from app.services import order_service

    order_service.transition(
        session,
        order_id=order.id,
        to_status=status,
        actor_type="vendor",
        actor_id=order.customer_id,
        now=at,
    )


def test_view_reads_units_and_event_duration(db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    shop = _shop(db_session)
    order = create_reserved_order(
        db_session,
        customer=customer,
        shop=shop,
        reserved_at=BASE,
        page_count=3,
        copies=2,
    )
    for status, at in (
        ("ACCEPTED", BASE + timedelta(minutes=1)),
        ("PRINTING", BASE + timedelta(minutes=2)),
        ("READY", BASE + timedelta(minutes=14)),
    ):
        order_service_transition(db_session, order, status, at)

    row = (
        db_session.execute(
            text(
                "SELECT print_units, print_minutes, completed_at, ready_event_id "
                "FROM order_print_durations WHERE order_id = :order_id"
            ),
            {"order_id": order.id},
        )
        .mappings()
        .one()
    )

    assert row["print_units"] == 6
    assert float(row["print_minutes"]) == 12
    assert row["completed_at"] == BASE + timedelta(minutes=14)
    assert row["ready_event_id"] > 0


def test_exact_quartiles_and_current_queue_work(db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    shop = _shop(db_session)
    speeds = [1, 2, 2, 3, 3, 3, 4, 4, 5, 9]
    for index, speed in enumerate(speeds):
        _completed(
            db_session,
            customer,
            shop,
            entry=BASE + timedelta(hours=index * 3),
            units=1,
            print_minutes=speed,
        )
    queued = create_reserved_order(
        db_session,
        customer=customer,
        shop=shop,
        reserved_at=BASE + timedelta(days=10),
        page_count=4,
    )

    estimate = estimate_service.get_wait_estimate(db_session, shop_id=shop.id)

    assert estimate.minimum_minutes == pytest.approx(9)
    assert estimate.median_minutes == pytest.approx(12)
    assert estimate.maximum_minutes == pytest.approx(16)
    assert estimate.sample_count == 10
    assert estimate.rough is False
    assert estimate.shop_id == queued.shop_id


def test_queue_includes_unfinished_cash_and_online_but_not_ready_or_unpaid(
    db_session: Session,
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    shop = _shop(db_session)
    for index in range(10):
        _completed(
            db_session,
            customer,
            shop,
            entry=BASE + timedelta(hours=index * 3),
            units=1,
            print_minutes=1,
        )
    create_unpaid_order(db_session, customer=customer, shop=shop, page_count=1)
    create_reserved_order(db_session, customer=customer, shop=shop, page_count=2)
    create_paid_order(db_session, customer=customer, shop=shop, page_count=4)
    accepted = create_reserved_order(db_session, customer=customer, shop=shop, page_count=6)
    order_service_transition(db_session, accepted, "ACCEPTED", BASE + timedelta(days=20))
    printing = create_reserved_order(db_session, customer=customer, shop=shop, page_count=8)
    order_service_transition(db_session, printing, "ACCEPTED", BASE + timedelta(days=20))
    order_service_transition(db_session, printing, "PRINTING", BASE + timedelta(days=20, minutes=1))
    ready = create_reserved_order(db_session, customer=customer, shop=shop, page_count=10)
    order_service_transition(db_session, ready, "ACCEPTED", BASE + timedelta(days=20))
    order_service_transition(db_session, ready, "PRINTING", BASE + timedelta(days=20, minutes=1))
    order_service_transition(db_session, ready, "READY", BASE + timedelta(days=20, minutes=2))

    estimate = estimate_service.get_wait_estimate(db_session, shop_id=shop.id)

    # 2 reserved + 4 paid + 6 accepted + 8 printing. The 1-page unpaid and
    # 10-page ready orders contribute nothing.
    assert estimate.median_minutes == pytest.approx(20)
    # The ten historical jobs plus the newly ready one are valid speed samples.
    assert estimate.sample_count == 11
    assert estimate.rough is False


def test_recent_fifty_filters_invalid_durations_before_choosing_samples(
    db_session: Session,
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    shop = _shop(db_session)
    _completed(
        db_session,
        customer,
        shop,
        entry=BASE - timedelta(days=1),
        units=1,
        print_minutes=100,
    )
    for index in range(50):
        _completed(
            db_session,
            customer,
            shop,
            entry=BASE + timedelta(hours=index * 3),
            units=1,
            print_minutes=1,
        )
    for index, duration in enumerate((0, -5)):
        _completed(
            db_session,
            customer,
            shop,
            entry=BASE + timedelta(days=10 + index),
            units=1,
            print_minutes=duration,
        )

    profile = estimate_service.speed_profiles_for_shops(db_session, [shop.id])[shop.id]

    assert profile.sample_count == 50
    assert profile.p25 == pytest.approx(1)
    assert profile.median == pytest.approx(1)
    assert profile.p75 == pytest.approx(1)
    assert profile.rough is False


def test_speed_cutoff_excludes_future_completion(db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    shop = _shop(db_session)
    cutoff = BASE + timedelta(days=30)
    for index in range(10):
        _completed(
            db_session,
            customer,
            shop,
            entry=BASE + timedelta(hours=index * 3),
            units=1,
            print_minutes=1,
        )
    _completed(
        db_session,
        customer,
        shop,
        entry=cutoff + timedelta(days=1),
        units=1,
        print_minutes=100,
    )

    before = estimate_service.speed_profiles_for_shops(db_session, [shop.id], as_of=cutoff)[shop.id]
    after = estimate_service.speed_profiles_for_shops(db_session, [shop.id])[shop.id]

    assert before.sample_count == 10
    assert before.median == pytest.approx(1)
    assert after.sample_count == 11
    assert after.median == pytest.approx(1)


def test_non_accepting_verified_shop_keeps_estimate_for_existing_customers(
    db_session: Session,
) -> None:
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor, accepting_orders=False)

    estimate = estimate_service.get_wait_estimate(db_session, shop_id=shop.id)

    assert estimate.rough is True
    assert estimate.sample_count == 0
    assert estimate.maximum_minutes == 0


def test_naive_cutoff_is_refused(db_session: Session) -> None:
    with pytest.raises(ValueError):
        estimate_service.speed_profiles_for_shops(
            db_session, [uuid.uuid4()], as_of=datetime(2026, 1, 1)
        )
