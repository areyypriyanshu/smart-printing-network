import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import User
from app.rate_limit import user_rate_limit
from app.schemas.admin import (
    AdminActionListResponse,
    AdminShopListResponse,
    AdminShopResponse,
    SuspendShopRequest,
)
from app.schemas.errors import ERROR_RESPONSES
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"], responses=ERROR_RESPONSES)

_admin_only = require_role("admin")


@router.get("/shops", response_model=AdminShopListResponse)
def list_shops(
    status: Literal["pending", "verified", "all"] = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    session: Session = Depends(get_db),
    _admin: User = Depends(_admin_only),
) -> AdminShopListResponse:
    """The shops the admin can act on, oldest first.

    `status` is `pending`, `verified` or `all`.
    """
    return admin_service.list_shops(session, status=status, limit=limit, cursor=cursor)


@router.post(
    "/shops/{shop_id}/approve",
    response_model=AdminShopResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "admin_actions"))],
)
def approve_shop(
    shop_id: uuid.UUID,
    session: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
) -> AdminShopResponse:
    return admin_service.approve_shop(session, shop_id=shop_id, admin_id=admin.id)


@router.post(
    "/shops/{shop_id}/suspend",
    response_model=AdminShopResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "admin_actions"))],
)
def suspend_shop(
    shop_id: uuid.UUID,
    body: SuspendShopRequest,
    session: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
) -> AdminShopResponse:
    """Take a shop off the market. Its existing orders are left alone."""
    return admin_service.suspend_shop(
        session, shop_id=shop_id, admin_id=admin.id, reason=body.reason
    )


@router.get("/actions", response_model=AdminActionListResponse)
def list_actions(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    session: Session = Depends(get_db),
    _admin: User = Depends(_admin_only),
) -> AdminActionListResponse:
    """The moderation log, newest first."""
    return admin_service.list_actions(session, limit=limit, cursor=cursor)
