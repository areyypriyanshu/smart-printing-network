import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.order_state import ACTIVE_STATUSES, SHOP_VISIBLE_STATUSES
from app.domain.pickup_code import verify_pickup_code
from app.errors import NotFound, PickupCodeInvalid
from app.gateways.storage import Storage
from app.models import Order, OrderEvent, Upload
from app.schemas.order import FileUrlResponse, OrderEventResponse
from app.schemas.vendor import (
    VendorOrderDetailResponse,
    VendorOrderResponse,
    VendorQueueResponse,
)
from app.services import order_service
from app.services.upload_service import presigned_download


def list_queue(session: Session, *, shop_id: uuid.UUID, limit: int) -> VendorQueueResponse:
    """The shop's active orders, oldest reservation first.

    First reserved, first served: the queue is ordered by `reserved_at`
    ascending, so the card at the top of the New column is the order that
    has been waiting longest. `reserved_at` is set when an order is paid
    for online and when it is reserved for cash, so the two methods queue
    the same way. It is served by `orders_queue_idx`.
    """
    orders = session.scalars(
        select(Order)
        .where(Order.shop_id == shop_id, Order.status.in_(ACTIVE_STATUSES))
        .order_by(Order.reserved_at.asc(), Order.order_no.asc())
        .limit(limit)
    )
    return VendorQueueResponse(
        items=[vendor_order_response(order) for order in orders],
        accept_timeout_minutes=get_settings().accept_timeout_min,
    )


def get_vendor_order(
    session: Session, *, order_id: uuid.UUID, shop_id: uuid.UUID
) -> VendorOrderDetailResponse:
    order = _shop_order(session, order_id=order_id, shop_id=shop_id)
    events = session.scalars(
        select(OrderEvent)
        .where(OrderEvent.order_id == order.id)
        .order_by(OrderEvent.at.asc(), OrderEvent.id.asc())
    )
    upload = session.get(Upload, order.upload_id)
    return VendorOrderDetailResponse(
        order=vendor_order_response(order),
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
        file_available=upload is not None and upload.file_deleted_at is None,
    )


def accept_order(
    session: Session, *, order_id: uuid.UUID, shop_id: uuid.UUID, vendor_id: uuid.UUID
) -> VendorOrderResponse:
    """Take a paid order. The shop now owes the customer a printout."""
    order = _shop_order(session, order_id=order_id, shop_id=shop_id)
    accepted = order_service.transition(
        session,
        order_id=order.id,
        to_status="ACCEPTED",
        actor_type="vendor",
        actor_id=vendor_id,
    )
    return vendor_order_response(accepted)


def reject_order(
    session: Session,
    *,
    order_id: uuid.UUID,
    shop_id: uuid.UUID,
    vendor_id: uuid.UUID,
    reason: str,
) -> VendorOrderResponse:
    """Turn a paid order down. The customer is refunded."""
    order = _shop_order(session, order_id=order_id, shop_id=shop_id)
    rejected = order_service.transition(
        session,
        order_id=order.id,
        to_status="REJECTED",
        actor_type="vendor",
        actor_id=vendor_id,
        reason=reason,
    )
    return vendor_order_response(rejected)


def start_order(
    session: Session, *, order_id: uuid.UUID, shop_id: uuid.UUID, vendor_id: uuid.UUID
) -> VendorOrderResponse:
    order = _shop_order(session, order_id=order_id, shop_id=shop_id)
    printing = order_service.transition(
        session,
        order_id=order.id,
        to_status="PRINTING",
        actor_type="vendor",
        actor_id=vendor_id,
    )
    return vendor_order_response(printing)


def mark_ready(
    session: Session, *, order_id: uuid.UUID, shop_id: uuid.UUID, vendor_id: uuid.UUID
) -> VendorOrderResponse:
    order = _shop_order(session, order_id=order_id, shop_id=shop_id)
    ready = order_service.transition(
        session,
        order_id=order.id,
        to_status="READY",
        actor_type="vendor",
        actor_id=vendor_id,
    )
    return vendor_order_response(ready)


def cancel_order(
    session: Session,
    *,
    order_id: uuid.UUID,
    shop_id: uuid.UUID,
    vendor_id: uuid.UUID,
    reason: str,
) -> VendorOrderResponse:
    """Cancel an order the shop has already accepted. The customer is refunded."""
    order = _shop_order(session, order_id=order_id, shop_id=shop_id)
    cancelled = order_service.transition(
        session,
        order_id=order.id,
        to_status="CANCELLED",
        actor_type="vendor",
        actor_id=vendor_id,
        reason=reason,
    )
    return vendor_order_response(cancelled)


def collect_order(
    session: Session,
    *,
    order_id: uuid.UUID,
    shop_id: uuid.UUID,
    vendor_id: uuid.UUID,
    code: str,
) -> VendorOrderResponse:
    """Hand the printout over, against the code the customer shows.

    The code is the only proof that the person at the counter is the person
    who paid, so it is compared in constant time and never revealed to the
    shop in any response.

    For a cash order this is also the moment the money changes hands. The
    capture is part of the transition, not a separate step, so the status
    change, the event row and the payment record commit together.
    """
    order = _shop_order(session, order_id=order_id, shop_id=shop_id)
    if order.pickup_code is None or not verify_pickup_code(order.pickup_code, code):
        raise PickupCodeInvalid("Code does not match")
    collected = order_service.transition(
        session,
        order_id=order.id,
        to_status="COLLECTED",
        actor_type="vendor",
        actor_id=vendor_id,
    )
    return vendor_order_response(collected)


def vendor_file_url(
    session: Session,
    storage: Storage,
    *,
    order_id: uuid.UUID,
    shop_id: uuid.UUID,
) -> FileUrlResponse:
    """A short-lived download link for the PDF the shop has to print."""
    order = _shop_order(session, order_id=order_id, shop_id=shop_id)
    upload = session.get(Upload, order.upload_id)
    if upload is None:
        raise NotFound("This file is no longer available")
    return presigned_download(storage, upload)


def vendor_order_response(order: Order) -> VendorOrderResponse:
    return VendorOrderResponse(
        id=order.id,
        order_no=order.order_no,
        status=order.status,
        status_reason=order.status_reason,
        upload_id=order.upload_id,
        page_count=order.page_count,
        copies=order.copies,
        paper_size=order.paper_size,
        color=order.color,
        duplex=order.duplex,
        price_paise=order.price_paise,
        payment_method=order.payment_method,
        reserved_at=order.reserved_at,
        paid_at=order.paid_at,
        created_at=order.created_at,
    )


def _shop_order(session: Session, *, order_id: uuid.UUID, shop_id: uuid.UUID) -> Order:
    """Load an order that belongs to this shop.

    An order of another shop is reported as missing rather than forbidden,
    so the response never confirms that someone else's order exists. An
    order of this shop that the customer has neither paid for nor reserved
    is also hidden: the shop has not agreed to print it yet, and it is not
    the shop's to look at.

    A cash order is the shop's from the moment it is reserved, even though
    no money has changed hands yet, so the guard is about the state of the
    order and not about whether it has been paid for.
    """
    order = session.scalar(select(Order).where(Order.id == order_id, Order.shop_id == shop_id))
    if order is None or order.status not in SHOP_VISIBLE_STATUSES:
        raise NotFound("Order not found")
    return order
