import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.order_state import (
    can_actor_transition,
    can_transition,
    is_terminal,
    queues_refund,
)
from app.domain.pickup_code import generate_pickup_code
from app.domain.pricing import quote_paise
from app.errors import (
    Conflict,
    Forbidden,
    InvalidTransition,
    NotFound,
    PaymentGatewayError,
    PriceChanged,
    RateNotSet,
    ShopUnavailable,
    UploadAlreadyUsed,
)
from app.gateways.payments import GatewayError, PaymentGateway
from app.gateways.storage import Storage
from app.models import Order, OrderEvent, Payment, Shop, ShopRate, Upload
from app.schemas.order import (
    FileUrlResponse,
    OrderCreateRequest,
    OrderDetailResponse,
    OrderEventResponse,
    OrderListResponse,
    OrderResponse,
)
from app.services.upload_service import get_upload, presigned_download

logger = logging.getLogger(__name__)


def create_order(
    session: Session,
    *,
    customer_id: uuid.UUID,
    request: OrderCreateRequest,
    idempotency_key: str,
    gateway: PaymentGateway,
) -> tuple[Order, Payment]:
    existing = session.scalar(
        select(Order).where(
            Order.customer_id == customer_id, Order.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        payment = session.scalar(select(Payment).where(Payment.order_id == existing.id))
        if payment is None:
            raise Conflict("The order exists but its payment is missing")
        return existing, payment

    upload = get_upload(session, upload_id=request.upload_id, customer_id=customer_id)
    already_used = session.scalar(select(Order.id).where(Order.upload_id == upload.id))
    if already_used is not None:
        raise UploadAlreadyUsed("This file is already attached to an order")

    shop = session.get(Shop, request.shop_id)
    if shop is None:
        raise NotFound("Shop not found")
    if not shop.is_verified or not shop.accepting_orders:
        raise ShopUnavailable("This shop is not accepting orders right now")

    rate = session.scalar(
        select(ShopRate).where(
            ShopRate.shop_id == shop.id,
            ShopRate.paper_size == request.paper_size,
            ShopRate.color == request.color,
            ShopRate.duplex == request.duplex,
        )
    )
    if rate is None:
        raise RateNotSet("This shop does not offer the selected options")

    price_paise = quote_paise(
        upload.page_count, request.copies, rate.rate_paise, shop.min_order_paise
    )
    if request.expected_price_paise is not None and request.expected_price_paise != price_paise:
        raise PriceChanged(
            "The price changed since the quote",
            details={"current_price_paise": price_paise},
        )

    order = Order(
        customer_id=customer_id,
        shop_id=shop.id,
        upload_id=upload.id,
        status="PENDING_PAYMENT",
        paper_size=request.paper_size,
        color=request.color,
        duplex=request.duplex,
        copies=request.copies,
        page_count=upload.page_count,
        rate_paise=rate.rate_paise,
        min_order_paise=shop.min_order_paise,
        price_paise=price_paise,
        idempotency_key=idempotency_key,
    )
    session.add(order)
    session.flush()
    session.add(
        OrderEvent(
            order_id=order.id,
            from_status=None,
            to_status="PENDING_PAYMENT",
            actor_type="customer",
            actor_id=customer_id,
        )
    )
    upload.delete_after = None
    session.commit()
    session.refresh(order)

    try:
        gateway_order = gateway.create_order(
            amount_paise=order.price_paise, receipt=str(order.id), currency="INR"
        )
    except GatewayError as exc:
        logger.error("order_gateway_error", extra={"order_id": str(order.id)})
        transition(
            session,
            order_id=order.id,
            to_status="CANCELLED",
            actor_type="system",
            reason="gateway_error",
        )
        raise PaymentGatewayError("The payment provider could not start the payment") from exc

    payment = Payment(
        order_id=order.id,
        provider=gateway_order.provider,
        provider_order_id=gateway_order.provider_order_id,
        amount_paise=gateway_order.amount_paise,
        currency=gateway_order.currency,
        status="CREATED",
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return order, payment


def transition(
    session: Session,
    *,
    order_id: uuid.UUID,
    to_status: str,
    actor_type: str,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise NotFound("Order not found")

    from_status = order.status
    if not can_transition(from_status, to_status):
        raise InvalidTransition(f"An order cannot move from {from_status} to {to_status}")
    if not can_actor_transition(actor_type, from_status, to_status):
        raise Forbidden("Your role cannot perform this transition")

    now = _now()
    values: dict[str, object] = {
        "status": to_status,
        "status_reason": reason,
        "updated_at": now,
    }
    if to_status == "PAID":
        values["paid_at"] = now
        values["pickup_code"] = generate_pickup_code()

    updated_id = session.scalar(
        update(Order)
        .where(Order.id == order_id, Order.status == from_status)
        .values(**values)
        .returning(Order.id)
    )
    if updated_id is None:
        raise Conflict("The order changed while you were working. Refresh and try again")

    if is_terminal(to_status):
        upload = session.get(Upload, order.upload_id)
        if upload is not None:
            upload.delete_after = now + timedelta(hours=get_settings().file_retention_hours)

    if queues_refund(from_status, to_status):
        _queue_refund(session, order_id=order_id, now=now)

    session.add(
        OrderEvent(
            order_id=order_id,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )
    )
    session.commit()
    session.refresh(order)
    return order


def list_orders(
    session: Session,
    *,
    customer_id: uuid.UUID,
    limit: int,
    cursor: int | None,
) -> OrderListResponse:
    query = select(Order).where(Order.customer_id == customer_id)
    if cursor is not None:
        query = query.where(Order.order_no < cursor)
    query = query.order_by(Order.order_no.desc()).limit(limit + 1)
    rows = list(session.scalars(query))
    has_more = len(rows) > limit
    items = rows[:limit]
    return OrderListResponse(
        items=[order_response(order) for order in items],
        next_cursor=items[-1].order_no if has_more and items else None,
    )


def get_order_detail(
    session: Session, *, order_id: uuid.UUID, customer_id: uuid.UUID
) -> OrderDetailResponse:
    order = session.scalar(
        select(Order).where(Order.id == order_id, Order.customer_id == customer_id)
    )
    if order is None:
        raise NotFound("Order not found")
    events = list(
        session.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == order.id)
            .order_by(OrderEvent.at.asc(), OrderEvent.id.asc())
        )
    )
    return OrderDetailResponse(
        order=order_response(order),
        events=[
            OrderEventResponse(
                from_status=event.from_status,
                to_status=event.to_status,
                actor_type=event.actor_type,
                reason=event.reason,
                at=event.at,
            )
            for event in events
        ],
    )


def cancel_order(session: Session, *, order_id: uuid.UUID, customer_id: uuid.UUID) -> OrderResponse:
    """Cancel an order the customer placed.

    Allowed while the order is still waiting for payment and after it is
    paid but before the shop accepts it. Once the shop has accepted, the
    order is the shop's to finish or cancel, so the transition is refused.
    """
    order = session.scalar(
        select(Order).where(Order.id == order_id, Order.customer_id == customer_id)
    )
    if order is None:
        raise NotFound("Order not found")
    cancelled = transition(
        session,
        order_id=order.id,
        to_status="CANCELLED",
        actor_type="customer",
        actor_id=customer_id,
    )
    return order_response(cancelled)


def customer_file_url(
    session: Session,
    storage: Storage,
    *,
    order_id: uuid.UUID,
    customer_id: uuid.UUID,
) -> FileUrlResponse:
    """A short-lived download link for the PDF the customer uploaded."""
    order = session.scalar(
        select(Order).where(Order.id == order_id, Order.customer_id == customer_id)
    )
    if order is None:
        raise NotFound("Order not found")
    upload = session.get(Upload, order.upload_id)
    if upload is None:
        raise NotFound("This file is no longer available")
    return presigned_download(storage, upload)


def order_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        order_no=order.order_no,
        status=order.status,
        status_reason=order.status_reason,
        shop_id=order.shop_id,
        upload_id=order.upload_id,
        page_count=order.page_count,
        copies=order.copies,
        paper_size=order.paper_size,
        color=order.color,
        duplex=order.duplex,
        rate_paise=order.rate_paise,
        min_order_paise=order.min_order_paise,
        price_paise=order.price_paise,
        pickup_code=order.pickup_code,
        paid_at=order.paid_at,
        created_at=order.created_at,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _queue_refund(session: Session, *, order_id: uuid.UUID, now: datetime) -> None:
    """Mark the order's payment as awaiting a refund.

    Only a captured payment has money in it. The refund job picks up
    `REFUND_PENDING` rows, so setting the status here is what turns a
    rejection or a cancellation into money actually going back to the
    customer. The status change, the event row and this flag all commit in
    the same transaction as the order status change.
    """
    payment = session.scalar(select(Payment).where(Payment.order_id == order_id))
    if payment is None or payment.status != "CAPTURED":
        return
    payment.status = "REFUND_PENDING"
    payment.refund_next_attempt_at = now
