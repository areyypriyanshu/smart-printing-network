import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_shop, get_storage
from app.errors import PickupCodeInvalid
from app.gateways.storage import Storage
from app.models import Shop
from app.rate_limit import (
    enforce_pickup_attempt_limit,
    get_rate_limiter,
    record_pickup_attempt,
    user_rate_limit,
)
from app.schemas.order import FileUrlResponse
from app.schemas.shop import (
    RateItem,
    RatesReplaceRequest,
    VendorShopResponse,
    VendorShopUpdate,
)
from app.schemas.vendor import (
    CollectRequest,
    ReasonRequest,
    VendorOrderDetailResponse,
    VendorOrderResponse,
    VendorQueueResponse,
)
from app.services import shop_service, vendor_service

router = APIRouter(prefix="/vendor", tags=["vendor"])


@router.get("/shop", response_model=VendorShopResponse)
def get_shop(
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorShopResponse:
    return shop_service.vendor_shop_response(session, shop)


@router.patch("/shop", response_model=VendorShopResponse)
def update_shop(
    body: VendorShopUpdate,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorShopResponse:
    updated = shop_service.update_vendor_shop(session, shop, body)
    return shop_service.vendor_shop_response(session, updated)


@router.get("/rates", response_model=list[RateItem])
def get_rates(
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> list[RateItem]:
    return shop_service.rate_items(shop_service.get_rates(session, shop.id))


@router.put("/rates", response_model=list[RateItem])
def replace_rates(
    body: RatesReplaceRequest,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> list[RateItem]:
    rows = shop_service.replace_rates(session, shop.id, body.rates)
    return shop_service.rate_items(rows)


@router.get(
    "/queue",
    response_model=VendorQueueResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "vendor_queue"))],
)
def get_queue(
    limit: int = Query(default=100, ge=1, le=200),
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorQueueResponse:
    return vendor_service.list_queue(session, shop_id=shop.id, limit=limit)


@router.get(
    "/orders/{order_id}",
    response_model=VendorOrderDetailResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "vendor_queue"))],
)
def get_vendor_order(
    order_id: uuid.UUID,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorOrderDetailResponse:
    return vendor_service.get_vendor_order(session, order_id=order_id, shop_id=shop.id)


@router.post(
    "/orders/{order_id}/accept",
    response_model=VendorOrderResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "vendor_actions"))],
)
def accept_order(
    order_id: uuid.UUID,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorOrderResponse:
    return vendor_service.accept_order(
        session, order_id=order_id, shop_id=shop.id, vendor_id=shop.owner_id
    )


@router.post(
    "/orders/{order_id}/reject",
    response_model=VendorOrderResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "vendor_actions"))],
)
def reject_order(
    order_id: uuid.UUID,
    body: ReasonRequest,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorOrderResponse:
    return vendor_service.reject_order(
        session,
        order_id=order_id,
        shop_id=shop.id,
        vendor_id=shop.owner_id,
        reason=body.reason,
    )


@router.post(
    "/orders/{order_id}/start",
    response_model=VendorOrderResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "vendor_actions"))],
)
def start_order(
    order_id: uuid.UUID,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorOrderResponse:
    return vendor_service.start_order(
        session, order_id=order_id, shop_id=shop.id, vendor_id=shop.owner_id
    )


@router.post(
    "/orders/{order_id}/ready",
    response_model=VendorOrderResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "vendor_actions"))],
)
def mark_ready(
    order_id: uuid.UUID,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorOrderResponse:
    return vendor_service.mark_ready(
        session, order_id=order_id, shop_id=shop.id, vendor_id=shop.owner_id
    )


@router.post(
    "/orders/{order_id}/cancel",
    response_model=VendorOrderResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "vendor_actions"))],
)
def cancel_order(
    order_id: uuid.UUID,
    body: ReasonRequest,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorOrderResponse:
    return vendor_service.cancel_order(
        session,
        order_id=order_id,
        shop_id=shop.id,
        vendor_id=shop.owner_id,
        reason=body.reason,
    )


@router.post(
    "/orders/{order_id}/collect",
    response_model=VendorOrderResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "vendor_actions"))],
)
def collect_order(
    order_id: uuid.UUID,
    body: CollectRequest,
    request: Request,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
) -> VendorOrderResponse:
    limiter = get_rate_limiter(request)
    enforce_pickup_attempt_limit(limiter, order_id)
    try:
        return vendor_service.collect_order(
            session,
            order_id=order_id,
            shop_id=shop.id,
            vendor_id=shop.owner_id,
            code=body.code,
        )
    except PickupCodeInvalid:
        record_pickup_attempt(limiter, order_id)
        raise


@router.get(
    "/orders/{order_id}/file",
    response_model=FileUrlResponse,
    dependencies=[Depends(user_rate_limit(30, 60, "vendor_actions"))],
)
def get_vendor_order_file(
    order_id: uuid.UUID,
    shop: Shop = Depends(get_current_shop),
    session: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> FileUrlResponse:
    return vendor_service.vendor_file_url(session, storage, order_id=order_id, shop_id=shop.id)
