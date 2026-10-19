import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_customer
from app.models import User
from app.rate_limit import user_rate_limit
from app.schemas.order import (
    OrderCreateRequest,
    OrderDetailResponse,
    OrderListResponse,
    OrderResponse,
)
from app.services import order_service

router = APIRouter(tags=["orders"])


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(user_rate_limit(20, 60, "orders"))],
)
def create_order(
    body: OrderCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> OrderResponse:
    order = order_service.create_order(
        session,
        customer_id=user.id,
        request=body,
        idempotency_key=idempotency_key,
    )
    return order_service.order_response(order)


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
