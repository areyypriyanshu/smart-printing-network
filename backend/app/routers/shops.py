import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import User
from app.schemas.shop import ShopListResponse, ShopResponse
from app.services import shop_service

router = APIRouter(prefix="/shops", tags=["shops"])

_customer_only = require_role("customer")


@router.get("", response_model=ShopListResponse)
def list_shops(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session: Session = Depends(get_db),
    _user: User = Depends(_customer_only),
) -> ShopListResponse:
    return shop_service.list_public_shops(session, limit=limit, cursor=cursor)


@router.get("/{shop_id}", response_model=ShopResponse)
def get_shop(
    shop_id: uuid.UUID,
    session: Session = Depends(get_db),
    _user: User = Depends(_customer_only),
) -> ShopResponse:
    return shop_service.get_public_shop(session, shop_id)
