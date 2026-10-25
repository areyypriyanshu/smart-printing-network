"""Put enough orders in one shop's queue to measure the queue endpoint.

This is load-test data, not product data, and it is labelled as such in
the filenames and the idempotency keys. The orders are made through the
real service, so they obey the same rules a customer's order does: the
price is computed by the pricing function, the pickup code is issued by
the same generator, and the event history is written by the same
transition.

Run it in the API container, against the local stack:

    docker compose run --rm -v "$PWD/perf:/perf" api \
        python /perf/seed_queue.py --orders 200

The script refuses to run in production. The orders it makes are
cash orders waiting at the counter. It does not take money and it does
not touch the object store.
"""

import argparse
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Order, OrderEvent, Payment, Shop, Upload, User
from app.schemas.order import OrderCreateRequest
from app.services import order_service

CUSTOMER_EMAIL = "perf-load@example.com"
KEY_PREFIX = "perf-load-"
FILE_PREFIX = "perf-load/"


def remove_previous(session) -> int:
    """Take out the orders and uploads an earlier run left behind."""
    order_ids = list(
        session.scalars(
            select(Order.id).where(Order.idempotency_key.like(f"{KEY_PREFIX}%"))
        )
    )
    if order_ids:
        session.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
        session.execute(delete(OrderEvent).where(OrderEvent.order_id.in_(order_ids)))
        session.execute(delete(Order).where(Order.id.in_(order_ids)))
    uploads = session.execute(
        delete(Upload).where(Upload.file_key.like(f"{FILE_PREFIX}%"))
    ).rowcount
    session.commit()
    return len(order_ids) + int(uploads or 0)


def customer_for(session) -> User:
    customer = session.scalar(select(User).where(User.email == CUSTOMER_EMAIL))
    if customer is not None:
        return customer
    customer = User(
        email=CUSTOMER_EMAIL,
        full_name="Load Test Customer",
        role="customer",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def shop_for(session, email: str) -> Shop:
    shop = session.scalar(
        select(Shop).join(User, User.id == Shop.owner_id).where(User.email == email)
    )
    if shop is None:
        raise SystemExit(
            f"No shop for {email}. Run `make seed` before seeding the queue."
        )
    return shop


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shop-email", default="vendor1@example.com")
    parser.add_argument("--orders", type=int, default=200)
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="remove the load-test orders without making new ones",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if settings.env == "production":
        raise SystemExit("The load-test seed is for local development only.")
    if args.orders < 1:
        raise SystemExit("--orders must be at least 1.")

    with SessionLocal() as session:
        removed = remove_previous(session)
        if removed:
            print(f"Removed {removed} rows from an earlier load-test run.")
        if args.cleanup:
            print("Cleanup complete.")
            return 0

        shop = shop_for(session, args.shop_email)
        customer = customer_for(session)
        now = datetime.now(UTC)

        for index in range(args.orders):
            upload = Upload(
                customer_id=customer.id,
                file_key=f"{FILE_PREFIX}{uuid.uuid4().hex}.pdf",
                original_filename="load-test.pdf",
                size_bytes=1024,
                sha256="0" * 64,
                page_count=1,
            )
            session.add(upload)
            session.commit()
            session.refresh(upload)
            order_service.create_order(
                session,
                customer_id=customer.id,
                request=OrderCreateRequest(
                    upload_id=upload.id,
                    shop_id=shop.id,
                    paper_size="A4",
                    color=False,
                    duplex=False,
                    copies=1,
                ),
                idempotency_key=f"{KEY_PREFIX}{uuid.uuid4().hex}",
                # Oldest first, so the queue has a believable order.
                now=now - timedelta(seconds=args.orders - index),
            )

        queued = session.scalar(
            select(func.count())
            .select_from(Order)
            .where(
                Order.shop_id == shop.id,
                Order.status == "RESERVED",
                Order.idempotency_key.like(f"{KEY_PREFIX}%"),
            )
        )
        print(
            f"Made {args.orders} reserved orders for {shop.name}. "
            f"{queued} are in its queue."
        )
        if queued != args.orders:
            print("The queue does not hold what was made.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
