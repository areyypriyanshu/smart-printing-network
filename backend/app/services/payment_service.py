import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import storable_json
from app.errors import (
    Conflict,
    InvalidTransition,
    PaymentNotApplied,
    ValidationError,
    WebhookSignatureInvalid,
)
from app.gateways.payments import PaymentGateway
from app.models import Order, Payment, WebhookEvent
from app.services import order_service

logger = logging.getLogger(__name__)

ORDER_PAID = "order.paid"
REFUND_PROCESSED = "refund.processed"
LATE_PAYMENT_STATUSES = ("EXPIRED", "CANCELLED")


def handle_webhook(
    session: Session,
    *,
    raw_body: bytes,
    signature: str,
    event_id: str,
    gateway: PaymentGateway,
) -> str:
    if not gateway.verify_webhook_signature(raw_body=raw_body, signature=signature):
        raise WebhookSignatureInvalid("Webhook signature does not match")

    # "Duplicate" means "already applied", not "already recorded". A delivery
    # that failed after the inbox row was written must stay reprocessable, so
    # the provider's retry can still apply it.
    event = session.get(WebhookEvent, event_id)
    if event is not None and event.processed_at is not None:
        return "duplicate"

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValidationError("Webhook body is not valid JSON") from exc

    event_type = str(payload.get("event", ""))
    if event is None:
        try:
            session.add(
                WebhookEvent(
                    event_id=event_id,
                    provider=gateway.provider,
                    event_type=event_type,
                    payload=storable_json(payload),
                )
            )
            # Flushed, not committed: the inbox row becomes durable together
            # with the effect, so a failure before the effect rolls the event
            # id back instead of spending it, and the provider's retry can
            # still apply it.
            session.flush()
        except IntegrityError:
            session.rollback()
            return "duplicate"

    if event_type == ORDER_PAID:
        outcome = _handle_order_paid(session, payload=payload)
    elif event_type == REFUND_PROCESSED:
        outcome = _handle_refund_processed(session, payload=payload)
    else:
        outcome = "ignored"

    event = session.get(WebhookEvent, event_id)
    if event is not None:
        event.processed_at = datetime.now(UTC)
        session.commit()
    return outcome


def _handle_order_paid(session: Session, *, payload: dict[str, Any]) -> str:
    payment_payload = payload.get("payload", {}).get("payment", {})
    provider_order_id = str(payment_payload.get("order_id", ""))
    provider_payment_id = str(payment_payload.get("id", ""))
    amount_paise = int(payment_payload.get("amount", 0))
    currency = str(payment_payload.get("currency", ""))

    payment = session.scalar(select(Payment).where(Payment.provider_order_id == provider_order_id))
    if payment is None:
        logger.error(
            "webhook_order_paid_without_payment",
            extra={"provider_order_id": provider_order_id},
        )
        return "unknown_order"

    order = session.get(Order, payment.order_id)
    if order is None:
        logger.error("webhook_order_paid_without_order", extra={"payment_id": str(payment.id)})
        return "unknown_order"

    if amount_paise != order.price_paise or currency != "INR":
        logger.error(
            "webhook_order_paid_amount_mismatch",
            extra={
                "order_id": str(order.id),
                "expected_paise": order.price_paise,
                "received_paise": amount_paise,
                "received_currency": currency,
            },
        )
        return "amount_mismatch"

    if provider_payment_id:
        duplicate = session.scalar(
            select(Payment).where(Payment.provider_payment_id == provider_payment_id)
        )
        if duplicate is not None and duplicate.id != payment.id:
            logger.error(
                "webhook_order_paid_duplicate_provider_payment_id",
                extra={"provider_payment_id": provider_payment_id},
            )
            return "duplicate_payment"
        payment.provider_payment_id = provider_payment_id

    if order.status == "PENDING_PAYMENT":
        # The capture and the state change are one operation: let the
        # transition's own commit write both, so a failed transition cannot
        # leave a captured payment behind.
        payment.status = "CAPTURED"
        try:
            order_service.transition(
                session, order_id=order.id, to_status="PAID", actor_type="webhook"
            )
        except (InvalidTransition, Conflict) as failure:
            session.rollback()
            refreshed = session.get(Order, order.id)
            status = refreshed.status if refreshed is not None else "unknown"
            if status in LATE_PAYMENT_STATUSES:
                # The order went terminal while the payment was landing. The
                # money was taken at the provider, so it has to go back. The
                # refund job selects on refund_next_attempt_at, so the
                # schedule is set here as well.
                late = session.get(Payment, payment.id)
                if late is None:
                    return "unknown_order"
                if provider_payment_id:
                    late.provider_payment_id = provider_payment_id
                late.status = "REFUND_PENDING"
                late.refund_next_attempt_at = datetime.now(UTC)
                session.commit()
                logger.error(
                    "webhook_late_payment_refund_queued",
                    extra={"order_id": str(order.id), "status": status},
                )
                return "refund_pending"
            # The provider can deliver two different events for the same
            # payment at the same moment. The first one moved the order to
            # PAID, so this one has nothing left to do. The money is captured
            # either way, and the order is paid, which is exactly what the two
            # deliveries together mean.
            if status == "PAID":
                logger.info(
                    "webhook_order_paid_already_applied",
                    extra={"order_id": str(order.id), "status": status},
                )
                return "already_paid"
            # The order is still waiting for its payment, so the capture
            # was not applied. The delivery is answered with a status that
            # says "try again", and the event is not recorded as applied,
            # so the provider's retry can still apply it.
            logger.error(
                "webhook_order_paid_not_applied",
                extra={"order_id": str(order.id), "status": status},
            )
            raise PaymentNotApplied("The payment could not be applied to the order") from failure
        return "paid"

    if order.status in LATE_PAYMENT_STATUSES:
        payment.status = "REFUND_PENDING"
        # The refund job only picks up a row that has a due time, so the
        # schedule has to be set here as well, or the money the provider
        # captured is never sent back.
        payment.refund_next_attempt_at = datetime.now(UTC)
        session.commit()
        logger.error(
            "webhook_late_payment_refund_queued",
            extra={"order_id": str(order.id), "status": order.status},
        )
        return "refund_pending"

    return "already_paid"


def _handle_refund_processed(session: Session, *, payload: dict[str, Any]) -> str:
    refund_payload = payload.get("payload", {}).get("refund", {})
    refund_id = str(refund_payload.get("id", ""))
    provider_payment_id = str(refund_payload.get("payment_id", ""))

    payment = session.scalar(
        select(Payment).where(Payment.provider_payment_id == provider_payment_id)
    )
    if payment is None:
        logger.error(
            "webhook_refund_without_payment",
            extra={"provider_payment_id": provider_payment_id},
        )
        return "unknown_payment"

    payment.status = "REFUNDED"
    if refund_id:
        payment.refund_id = refund_id
    session.commit()
    return "refunded"
