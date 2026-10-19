"""Turn away paid orders that no shop picked up.

A customer has already paid when the order reaches the queue. If no shop
accepts it within the accept window, the order is rejected and the
customer is refunded. The refund is queued by the transition itself, in
the same transaction, so the money is never left unaccounted for.
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
REASON = "shop_timeout"


def run(session: Session, *, now: datetime) -> int:
    """Reject paid orders that have been waiting too long for a shop.

    Returns how many orders were rejected. Safe to run twice.
    """
    settings = get_settings()
    cutoff = now - timedelta(minutes=settings.accept_timeout_min)
    order_ids = list(
        session.scalars(
            select(Order.id)
            .where(Order.status == "PAID", Order.paid_at < cutoff)
            .order_by(Order.paid_at.asc())
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )

    rejected = 0
    for order_id in order_ids:
        try:
            order_service.transition(
                session,
                order_id=order_id,
                to_status="REJECTED",
                actor_type="system",
                reason=REASON,
                now=now,
            )
        except Conflict:
            logger.info("auto_reject_conflict", extra={"order_id": str(order_id)})
            continue
        rejected += 1
    return rejected
