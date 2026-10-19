"""Expire orders the customer never came to collect.

A cash order that is ready and waiting for the customer to turn up is
holding a file and a shop's attention. If the customer does not come, the
job expires it, which releases the file for deletion and takes the order
out of the shop's queue.

Only cash orders are expired here. An online order has been paid for, and
expiring it would take the customer's money without giving it back: the
state machine does not queue a refund for a ready order, because the
money was captured at payment time and giving it back is a decision that
needs a refund path of its own. That is a separate piece of work.
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
REASON = "no_show"


def run(session: Session, *, now: datetime) -> int:
    """Expire cash orders that have been ready for too long.

    Returns how many orders were expired. Safe to run twice: the second
    run finds nothing, because the first run already moved them out.
    """
    settings = get_settings()
    cutoff = now - timedelta(hours=settings.no_show_timeout_hours)
    order_ids = list(
        session.scalars(
            select(Order.id)
            .where(
                Order.status == "READY",
                Order.payment_method == "at_store",
                Order.ready_at < cutoff,
            )
            .order_by(Order.ready_at.asc())
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
            logger.info("expire_no_shows_conflict", extra={"order_id": str(order_id)})
            continue
        expired += 1
    return expired
