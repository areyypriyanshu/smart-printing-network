"""Deterministic, clearly labelled simulated order history for local evaluation."""

import hashlib
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.gateways.identity.fake import dev_subject_for
from app.gateways.payments import CashGateway
from app.models import Order, OrderEvent, Payment, QualityReport, Shop, Upload, User
from app.schemas.order import OrderCreateRequest
from app.services import order_service

SIMULATED_HISTORY_PREFIX = "simulated-history-v1-"
SIMULATED_FILE_PREFIX = "simulated-history/v1/"
SIMULATED_CUSTOMER_EMAIL = "simulated-history@example.com"


def seed_history(
    session: Session,
    *,
    orders_per_shop: int = 30,
    seed: int = 9,
    now: datetime | None = None,
) -> int:
    """Create completed cash orders through the real order services.

    No object is stored. The uploads are metadata-only and are tombstoned at
    their simulated retention deadline, so the worker never asks S3 for them.
    Run this through `make seed-history`, which stops the worker while the
    backdated intermediate PAID/RESERVED states are being written.
    """
    settings = get_settings()
    if settings.env == "production":
        raise SystemExit("The simulated-history seed is for local development only.")
    if not settings.cash_at_store_enabled:
        raise SystemExit("Cash orders are off. Set CASH_AT_STORE_ENABLED=true first.")
    if orders_per_shop < 1 or orders_per_shop > 100:
        raise SystemExit("--orders-per-shop must be between 1 and 100.")
    current = datetime.now(UTC) if now is None else now
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("the history clock must be timezone-aware")

    shops = list(
        session.scalars(
            select(Shop)
            .where(Shop.is_verified.is_(True), Shop.accepting_orders.is_(True))
            .order_by(Shop.created_at, Shop.id)
        )
    )
    if not shops:
        raise SystemExit("No verified shops. Run `make seed` before `make seed-history`.")

    _remove_previous(session)
    customer = _customer(session)
    gateway = CashGateway()
    made = 0
    for shop_index, shop in enumerate(shops):
        rng = random.Random(seed + shop_index * 1009)
        speed = (0.18, 0.32, 0.48)[shop_index % 3]
        burst_count = (orders_per_shop + 4) // 5
        for burst in range(burst_count):
            burst_start = (
                current
                - timedelta(days=(burst_count - burst) * 5)
                + timedelta(hours=shop_index * 3)
            )
            scheduled = []
            previous_ready: datetime | None = None
            for position in range(5):
                index = burst * 5 + position
                if index >= orders_per_shop:
                    break
                entry = burst_start + timedelta(minutes=position * 3 + rng.random() * 2)
                pages = rng.choice([1, 2, 3, 5, 8, 12, 20])
                copies = rng.choice([1, 1, 1, 2, 3])
                accepted = entry + timedelta(minutes=0.5 + rng.random() * 2.5)
                earliest_start = accepted + timedelta(minutes=0.5 + rng.random() * 2)
                printing = earliest_start
                if previous_ready is not None:
                    printing = max(
                        earliest_start,
                        previous_ready + timedelta(minutes=0.25 + rng.random()),
                    )
                units = pages * copies
                duration = max(0.5, units * speed * (0.75 + rng.random() * 0.55))
                ready = printing + timedelta(minutes=duration)
                collected = ready + timedelta(minutes=15 + rng.random() * 105)
                previous_ready = ready
                scheduled.append(
                    (index, entry, pages, copies, accepted, printing, ready, collected)
                )

            # Create the burst first so each order has other work behind it.
            pending: list[tuple[Order, Upload, datetime, datetime, datetime, datetime]] = []
            for index, entry, pages, copies, accepted, printing, ready, collected in scheduled:
                upload = Upload(
                    customer_id=customer.id,
                    file_key=f"{SIMULATED_FILE_PREFIX}{shop.id}/{index}.pdf",
                    original_filename="simulated-history.pdf",
                    size_bytes=1024,
                    sha256=hashlib.sha256(f"{shop.id}:{index}".encode()).hexdigest(),
                    page_count=pages,
                    source_format="pdf",
                    created_at=entry,
                    delete_after=entry + timedelta(hours=24),
                )
                session.add(upload)
                session.commit()
                session.refresh(upload)
                order, _payment = order_service.create_order(
                    session,
                    customer_id=customer.id,
                    request=OrderCreateRequest(
                        upload_id=upload.id,
                        shop_id=shop.id,
                        paper_size="A4",
                        color=False,
                        duplex=False,
                        copies=copies,
                        payment_method="at_store",
                    ),
                    idempotency_key=f"{SIMULATED_HISTORY_PREFIX}{shop.id}-{index}",
                    gateway=gateway,
                    now=entry,
                )
                pending.append((order, upload, accepted, printing, ready, collected))

            for order, upload, accepted, printing, ready, collected in pending:
                for status, at in (
                    ("ACCEPTED", accepted),
                    ("PRINTING", printing),
                    ("READY", ready),
                    ("COLLECTED", collected),
                ):
                    order = order_service.transition(
                        session,
                        order_id=order.id,
                        to_status=status,
                        actor_type="vendor",
                        actor_id=shop.owner_id,
                        now=at,
                    )
                upload.file_deleted_at = collected + timedelta(hours=24)
                session.commit()
                made += 1
    return made


def _remove_previous(session: Session) -> None:
    # Idempotency keys are chosen by customers, so they cannot establish
    # ownership of the simulated dataset. Only server-generated storage keys
    # in this reserved namespace are safe to clean up.
    upload_ids = list(
        session.scalars(select(Upload.id).where(Upload.file_key.like(f"{SIMULATED_FILE_PREFIX}%")))
    )
    order_ids = (
        list(session.scalars(select(Order.id).where(Order.upload_id.in_(upload_ids))))
        if upload_ids
        else []
    )
    if order_ids:
        session.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
        session.execute(delete(OrderEvent).where(OrderEvent.order_id.in_(order_ids)))
        session.execute(delete(Order).where(Order.id.in_(order_ids)))
    if upload_ids:
        session.execute(delete(QualityReport).where(QualityReport.upload_id.in_(upload_ids)))
        session.execute(delete(Upload).where(Upload.id.in_(upload_ids)))
    session.commit()


def _customer(session: Session) -> User:
    customer = session.scalar(select(User).where(User.email == SIMULATED_CUSTOMER_EMAIL))
    if customer is not None:
        return customer
    customer = User(
        email=SIMULATED_CUSTOMER_EMAIL,
        clerk_user_id=dev_subject_for(SIMULATED_CUSTOMER_EMAIL),
        full_name="Simulated History Customer",
        role="customer",
        email_verified=True,
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer
