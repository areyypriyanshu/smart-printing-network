"""Send the money back.

A rejected or cancelled order leaves its payment in `REFUND_PENDING`.
This job calls the payment gateway to refund it, and retries with a
backoff when the gateway fails. The refund reference is derived from the
payment id, so a retry can never move the money twice.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.refunds import refund_backoff_seconds
from app.gateways.payments import GatewayError, PaymentGateway
from app.models import Payment

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


def run(session: Session, *, now: datetime, gateway: PaymentGateway) -> int:
    """Refund the payments that are waiting for a refund.

    Returns how many refunds were sent. Safe to run twice: a payment that
    has been refunded is no longer `REFUND_PENDING`, so the second run
    skips it.
    """
    payment_ids = list(
        session.scalars(
            select(Payment.id)
            .where(
                Payment.status == "REFUND_PENDING",
                Payment.refund_next_attempt_at.is_not(None),
                Payment.refund_next_attempt_at <= now,
            )
            .order_by(Payment.refund_next_attempt_at.asc())
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )

    refunded = 0
    for payment_id in payment_ids:
        payment = session.get(Payment, payment_id)
        if payment is None or payment.status != "REFUND_PENDING":
            continue
        if payment.provider_payment_id is None:
            # Nothing was ever captured, so there is nothing to give back.
            logger.error(
                "refund_without_provider_payment_id",
                extra={"payment_id": str(payment.id)},
            )
            payment.status = "FAILED"
            session.commit()
            continue

        try:
            result = gateway.refund(
                provider_payment_id=payment.provider_payment_id,
                amount_paise=payment.amount_paise,
                idempotency_note=f"refund:{payment.id}",
            )
        except GatewayError as exc:
            payment.refund_attempts += 1
            payment.refund_next_attempt_at = now + timedelta(
                seconds=refund_backoff_seconds(payment.refund_attempts)
            )
            session.commit()
            logger.error(
                "refund_attempt_failed",
                extra={
                    "payment_id": str(payment.id),
                    "attempts": payment.refund_attempts,
                    "reason": str(exc),
                },
            )
            continue

        payment.status = "REFUNDED"
        payment.refund_id = result.refund_id
        payment.refund_next_attempt_at = None
        session.commit()
        refunded += 1
    return refunded
