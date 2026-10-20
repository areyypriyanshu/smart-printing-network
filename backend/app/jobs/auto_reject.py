"""Turn away orders that no shop picked up.

An order reaches the shop's queue once it is paid for online, or once it
is reserved for cash. If no shop accepts it within the accept window, the
order is rejected.

For an online order the customer has already paid, so the refund is
queued by the transition itself, in the same transaction, and the money
is never left unaccounted for. For a cash order no money was taken, so
there is nothing to give back: the transition does not queue a refund,
because a reserved order is not one of the states that can be refunded.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import Conflict
from app.models import Order
from app.services import order_service

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
REASON = "shop_timeout"


def run(session: Session, *, now: datetime) -> int:
    """Reject orders that have been waiting too long for a shop.

    Returns how many orders were rejected. Safe to run twice: the second
    run finds nothing, because the first run already moved them out.
    """
    settings = get_settings()
    cutoff = now - timedelta(minutes=settings.accept_timeout_min)
    order_ids = list(
        session.scalars(
            select(Order.id)
            .where(
                Order.status.in_(("PAID", "RESERVED")),
                # `reserved_at` is the queue timestamp, but an order paid by
                # the previous application version, during a deployment, has
                # no value there. Falling back to `paid_at` reproduces the
                # behaviour of the previous version for exactly those rows,
                # so a stranded order is still rejected and refunded.
                func.coalesce(Order.reserved_at, Order.paid_at) < cutoff,
            )
            .order_by(func.coalesce(Order.reserved_at, Order.paid_at).asc())
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
