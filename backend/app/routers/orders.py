import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_customer, get_payment_gateway, get_storage
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
)
from app.services import order_service

router = APIRouter(tags=["orders"], responses=ERROR_RESPONSES)


@router.post(
    "/orders",
    response_model=OrderCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(user_rate_limit(20, 60, "orders"))],
)
def create_order(
    body: OrderCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    user: User = Depends(get_customer),
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
            key_id=gateway.checkout_key_id,
        ),
    )


@router.get(
    "/orders",
    response_model=OrderListResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "orders_list"))],
)
def list_orders(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None, ge=1),
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> OrderListResponse:
    return order_service.list_orders(session, customer_id=user.id, limit=limit, cursor=cursor)


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
