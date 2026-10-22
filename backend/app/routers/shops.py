import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_geocoder, require_role
from app.gateways.geocoding import Geocoder
from app.models import User
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.shop import (
    ShopListResponse,
    ShopResponse,
    ShopSearchQuery,
    ShopSearchResponse,
)
from app.services import search_service, shop_service

router = APIRouter(prefix="/shops", tags=["shops"], responses=ERROR_RESPONSES)

_customer_only = require_role("customer")


@router.get("", response_model=ShopListResponse)
def list_shops(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session: Session = Depends(get_db),
    _user: User = Depends(_customer_only),
) -> ShopListResponse:
    return shop_service.list_public_shops(session, limit=limit, cursor=cursor)


@router.get("/nearby", response_model=ShopListResponse)
def list_nearby_shops(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_m: int = Query(default=5000, ge=100, le=50000),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
    _user: User = Depends(_customer_only),
) -> ShopListResponse:
    """The shops around a point, nearest first.

    The radius is in metres. A shop further away than the radius is not
    returned, so a customer in a town with no shop is told that rather
    than shown one that is a hundred kilometres away.
    """
    return shop_service.list_nearby_shops(
        session,
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
        limit=limit,
    )


@router.get("/search", response_model=ShopSearchResponse)
def search_shops(
    query: Annotated[ShopSearchQuery, Query()],
    session: Session = Depends(get_db),
    _user: User = Depends(_customer_only),
    geocoder: Geocoder | None = Depends(get_geocoder),
) -> ShopSearchResponse:
    """The shops around the customer, with what they would charge.

    The customer may say where they are by sharing the browser's
    location, or by typing an address, or not at all. With no place at
    all, every shop is returned and the order is the server's to
    choose.

    When a file and the print options are given, each shop carries the
    price for that job. The price comes from the same function the
    order flow uses, so it is the price that would be charged. A shop
    that does not offer those options is left out.
    """
    return search_service.search_shops(
        session, customer_id=_user.id, query=query, geocoder=geocoder
    )


@router.get("/{shop_id}", response_model=ShopResponse)
def get_shop(
    shop_id: uuid.UUID,
    session: Session = Depends(get_db),
    _user: User = Depends(_customer_only),
) -> ShopResponse:
    return shop_service.get_public_shop(session, shop_id)
