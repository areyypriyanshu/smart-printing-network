from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_shop
from app.models import Shop
from app.schemas.shop import (
    RateItem,
    RatesReplaceRequest,
    VendorShopResponse,
    VendorShopUpdate,
)
from app.services import shop_service

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
