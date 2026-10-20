import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_customer, get_payment_gateway, get_storage, require_verified_email
from app.gateways.payments import PaymentGateway
from app.gateways.storage import Storage
from app.models import User
from app.rate_limit import user_rate_limit
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.order import (
    FileUrlResponse,
    OrderCreateRequest,
    OrderCreateResponse,
    OrderDetailResponse,
    OrderListResponse,
    OrderResponse,
    PaymentCheckoutResponse,
    ReorderResponse,
)
from app.services import order_service

router = APIRouter(tags=["orders"], responses=ERROR_RESPONSES)

#: The largest number a bigint column can hold. The cursor of this list is
#: an order number, and the column is a bigint, so a cursor above this is
#: refused at the edge rather than being handed to the database, which
#: answers with a server error instead of a rejection.
MAX_CURSOR = 2**63 - 1


@router.post(
    "/orders",
    response_model=OrderCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(user_rate_limit(20, 60, "orders"))],
)
def create_order(
    body: OrderCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    user: User = Depends(require_verified_email),
    session: Session = Depends(get_db),
    gateway: PaymentGateway = Depends(get_payment_gateway),
) -> OrderCreateResponse:
    order, payment = order_service.create_order(
        session,
        customer_id=user.id,
        request=body,
        idempotency_key=idempotency_key,
        gateway=gateway,
    )
    return OrderCreateResponse(
        order=order_service.order_response(order),
        payment=PaymentCheckoutResponse(
            provider=payment.provider,
            provider_order_id=payment.provider_order_id,
            amount_paise=payment.amount_paise,
            currency=payment.currency,
            # Only an order that is paid online has a checkout to open. A
            # cash order is paid at the counter, so it gets no key.
            key_id=(gateway.checkout_key_id if payment.provider == gateway.provider else None),
        ),
    )


@router.get(
    "/orders",
    response_model=OrderListResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "orders_list"))],
)
def list_orders(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None, ge=1, le=MAX_CURSOR),
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> OrderListResponse:
    return order_service.list_orders(session, customer_id=user.id, limit=limit, cursor=cursor)


@router.post(
    "/orders/{order_id}/reorder",
    response_model=ReorderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(user_rate_limit(10, 60, "reorder"))],
)
def reorder_order(
    order_id: uuid.UUID,
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> ReorderResponse:
    """Print the same job again, while the file is still stored.

    The file is copied, so the new order has its own file and its own
    retention window. When the file has already been deleted the answer
    is `FILE_UNAVAILABLE` and the customer uploads it again.
    """
    return order_service.reorder(session, storage, order_id=order_id, customer_id=user.id)


@router.get(
    "/orders/{order_id}",
    response_model=OrderDetailResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "orders_list"))],
)
def get_order(
    order_id: uuid.UUID,
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> OrderDetailResponse:
    return order_service.get_order_detail(session, order_id=order_id, customer_id=user.id)


@router.post(
    "/orders/{order_id}/cancel",
    response_model=OrderResponse,
    dependencies=[Depends(user_rate_limit(20, 60, "orders"))],
)
def cancel_order(
    order_id: uuid.UUID,
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> OrderResponse:
    return order_service.cancel_order(session, order_id=order_id, customer_id=user.id)


@router.get(
    "/orders/{order_id}/file",
    response_model=FileUrlResponse,
    dependencies=[Depends(user_rate_limit(30, 60, "order_file"))],
)
def get_order_file(
    order_id: uuid.UUID,
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> FileUrlResponse:
    return order_service.customer_file_url(session, storage, order_id=order_id, customer_id=user.id)
