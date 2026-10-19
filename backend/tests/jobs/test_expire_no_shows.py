"""Tests for the expire_no_shows job.

A cash order that is ready and waiting is holding a file and a shop's
attention. If the customer never turns up, the job expires it.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.config import get_settings
from app.gateways.payments import CashGateway
from app.jobs import expire_no_shows
from app.models import (
    Order,
    OrderEvent,
    Payment,
    RefreshToken,
    Shop,
    ShopRate,
    Upload,
    User,
)
from app.schemas.order import OrderCreateRequest
from app.services import order_service
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from tests.factories import (
    create_full_rate_table,
    create_paid_order,
    create_reserved_order,
    create_shop,
    create_upload_row,
    create_user,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _customer_and_shop(session: Session) -> tuple[object, object]:
    customer = create_user(session, email="customer@example.com")
    vendor = create_user(session, email="vendor@example.com", role="vendor")
    shop = create_shop(session, owner=vendor)
    create_full_rate_table(session, shop)
    return customer, shop


def _ready_cash_order(session: Session, *, hours_ago: int) -> object:
    """A cash order the shop has finished and is waiting for."""
    from app.services import order_service

    customer, shop = _customer_and_shop(session)
    order = create_reserved_order(session, customer=customer, shop=shop)
    for to_status in ("ACCEPTED", "PRINTING"):
        order_service.transition(
            session, order_id=order.id, to_status=to_status, actor_type="vendor"
        )
    order_service.transition(
        session,
        order_id=order.id,
        to_status="READY",
        actor_type="vendor",
        now=NOW - timedelta(hours=hours_ago),
    )
    return order


def test_a_cash_order_nobody_collected_is_expired(db_session: Session) -> None:
    order = _ready_cash_order(db_session, hours_ago=30)

    expired = expire_no_shows.run(db_session, now=NOW)

    assert expired == 1
    db_session.refresh(order)
    assert order.status == "EXPIRED"
    assert order.status_reason == "no_show"


def test_a_cash_order_inside_the_window_is_left_alone(db_session: Session) -> None:
    order = _ready_cash_order(db_session, hours_ago=2)

    expired = expire_no_shows.run(db_session, now=NOW)

    assert expired == 0
    db_session.refresh(order)
    assert order.status == "READY"


def test_running_the_job_twice_expires_nothing_the_second_time(
    db_session: Session,
) -> None:
    _ready_cash_order(db_session, hours_ago=30)

    first = expire_no_shows.run(db_session, now=NOW)
    second = expire_no_shows.run(db_session, now=NOW)

    assert first == 1
    assert second == 0


def test_expiry_writes_an_event(db_session: Session) -> None:
    order = _ready_cash_order(db_session, hours_ago=30)

    expire_no_shows.run(db_session, now=NOW)

    events = list(
        db_session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == order.id)
            .order_by(OrderEvent.at.asc(), OrderEvent.id.asc())
        )
    )
    assert events[-1].to_status == "EXPIRED"
    assert events[-1].actor_type == "system"
    assert events[-1].reason == "no_show"


def test_expiry_releases_the_file_for_deletion(db_session: Session) -> None:
    """The purge job cleans the PDF up once the order is done."""
    order = _ready_cash_order(db_session, hours_ago=30)

    expire_no_shows.run(db_session, now=NOW)

    upload = db_session.get(Upload, order.upload_id)
    assert upload is not None
    assert upload.delete_after is not None


def test_expiry_queues_no_refund(db_session: Session) -> None:
    """No money was taken, so there is nothing to give back."""
    order = _ready_cash_order(db_session, hours_ago=30)

    expire_no_shows.run(db_session, now=NOW)

    payment = db_session.scalar(select(Payment).where(Payment.order_id == order.id))
    assert payment is not None
    assert payment.status == "CREATED"
    assert payment.refund_next_attempt_at is None


def test_a_paid_order_nobody_collected_is_not_expired(db_session: Session) -> None:
    """An online order has the customer's money in it.

    Expiring it would take that money without giving it back, so the job
    leaves it alone. A paid order that is never collected needs a
    different decision, and a refund path of its own.
    """
    from app.services import order_service

    customer, shop = _customer_and_shop(db_session)
    order = create_paid_order(db_session, customer=customer, shop=shop)
    for to_status in ("ACCEPTED", "PRINTING"):
        order_service.transition(
            db_session, order_id=order.id, to_status=to_status, actor_type="vendor"
        )
    order_service.transition(
        db_session,
        order_id=order.id,
        to_status="READY",
        actor_type="vendor",
        now=NOW - timedelta(hours=30),
    )

    expired = expire_no_shows.run(db_session, now=NOW)

    assert expired == 0
    db_session.refresh(order)
    assert order.status == "READY"


def test_a_cash_order_that_is_not_ready_yet_is_not_expired(
    db_session: Session,
) -> None:
    """Only a job the shop has finished is waiting for a customer."""
    from app.services import order_service

    customer, shop = _customer_and_shop(db_session)
    order = create_reserved_order(db_session, customer=customer, shop=shop)
    order_service.transition(
        db_session,
        order_id=order.id,
        to_status="ACCEPTED",
        actor_type="vendor",
        now=NOW - timedelta(hours=30),
    )

    expired = expire_no_shows.run(db_session, now=NOW)

    assert expired == 0
    db_session.refresh(order)
    assert order.status == "ACCEPTED"


def test_two_workers_running_at_the_same_time_expire_it_once(
    race_engine,
) -> None:
    """The rows are claimed with SKIP LOCKED, so the work is not doubled.

    This test uses real connections and real threads, because a
    sequential test cannot show a race. It commits its own data and
    cleans up after itself.
    """
    order_id, run_id, customer_id, upload_id = _seed_ready_cash_order(race_engine)
    try:
        first, second = _run_in_parallel(race_engine)

        assert first + second == 1
        with Session(race_engine) as session:
            order = session.get(Order, order_id)
            assert order is not None
            assert order.status == "EXPIRED"
    finally:
        _cleanup(race_engine, customer_id, order_id, run_id, upload_id)


@pytest.fixture
def race_engine():
    url = make_url(get_settings().database_url).set(database="spn_test")
    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()


def _seed_ready_cash_order(engine) -> tuple[uuid.UUID, str, uuid.UUID]:
    """A cash order that is ready and has been waiting too long."""
    run_id = uuid.uuid4().hex[:8]
    with Session(engine) as session:
        customer = create_user(session, email=f"noshow-{run_id}@example.com")
        vendor = create_user(session, email=f"noshow-vendor-{run_id}@example.com", role="vendor")
        shop = create_shop(session, owner=vendor, name=f"No Show Shop {run_id}")
        create_full_rate_table(session, shop)
        upload = create_upload_row(session, customer=customer, page_count=1)
        order, _payment = order_service.create_order(
            session,
            customer_id=customer.id,
            request=OrderCreateRequest(
                upload_id=upload.id,
                shop_id=shop.id,
                paper_size="A4",
                color=False,
                duplex=False,
                copies=1,
                payment_method="at_store",
            ),
            idempotency_key=uuid.uuid4().hex,
            gateway=CashGateway(),
        )
        for to_status in ("ACCEPTED", "PRINTING"):
            order_service.transition(
                session, order_id=order.id, to_status=to_status, actor_type="vendor"
            )
        order_service.transition(
            session,
            order_id=order.id,
            to_status="READY",
            actor_type="vendor",
            now=NOW - timedelta(hours=30),
        )
        order_id = order.id
        customer_id = customer.id
        upload_id = upload.id
        session.commit()
    return order_id, run_id, customer_id, upload_id


def _run_in_parallel(engine) -> tuple[int, int]:
    """Run the job twice at the same time, in two real threads."""
    results: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def run() -> None:
        try:
            barrier.wait()
            with Session(engine) as session:
                results.append(expire_no_shows.run(session, now=NOW))
        except BaseException as exc:  # noqa: BLE001 - the test asserts on it
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    return results[0], results[1]


def _cleanup(
    engine,
    customer_id: uuid.UUID,
    order_id: uuid.UUID,
    run_id: str,
    upload_id: uuid.UUID,
) -> None:
    """Remove what this test really committed."""
    with Session(engine) as session:
        session.execute(delete(OrderEvent).where(OrderEvent.order_id == order_id))
        session.execute(delete(Payment).where(Payment.order_id == order_id))
        session.execute(delete(Order).where(Order.id == order_id))
        session.execute(delete(Upload).where(Upload.id == upload_id))
        session.execute(
            delete(ShopRate).where(
                ShopRate.shop_id.in_(
                    select(Shop.id).where(Shop.name.like(f"No Show Shop {run_id}%"))
                )
            )
        )
        session.execute(delete(Shop).where(Shop.name.like(f"No Show Shop {run_id}%")))
        session.execute(delete(RefreshToken).where(RefreshToken.user_id == customer_id))
        session.execute(delete(User).where(User.email.like(f"%{run_id}@example.com")))
        session.commit()
