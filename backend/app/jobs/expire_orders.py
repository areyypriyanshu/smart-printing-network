"""Expire orders whose payment window closed.

An order that nobody paid for is worthless after fifteen minutes: the
upload it holds should be released and the customer should not be able to
come back and pay for a stale order later.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import Conflict
from app.models import Order
from app.services import order_service

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
REASON = "payment_timeout"


def run(session: Session, *, now: datetime) -> int:
    """Expire unpaid orders that are past the payment window.

    Returns how many orders were expired. Safe to run twice: the second
    run finds nothing, because the first run already moved them out of
    `PENDING_PAYMENT`.
    """
    settings = get_settings()
    cutoff = now - timedelta(minutes=settings.payment_timeout_min)
    order_ids = list(
        session.scalars(
            select(Order.id)
            .where(Order.status == "PENDING_PAYMENT", Order.created_at < cutoff)
            .order_by(Order.created_at.asc())
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )

    expired = 0
    for order_id in order_ids:
        try:
            order_service.transition(
                session,
                order_id=order_id,
                to_status="EXPIRED",
                actor_type="system",
                reason=REASON,
                now=now,
            )
        except Conflict:
            # Another worker got there first. That is the expected outcome
            # of running two workers, not a failure.
            logger.info("expire_orders_conflict", extra={"order_id": str(order_id)})
            continue
        expired += 1
    return expired
