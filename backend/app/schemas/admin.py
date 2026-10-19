import uuid
from datetime import datetime

from pydantic import BaseModel, Field

MAX_REASON_LENGTH = 500


class AdminShopResponse(BaseModel):
    """A shop as the admin sees it.

    The owner email and name are here because verifying a shop means
    checking that a real person is behind it. Nothing about a customer's
    orders or money is reachable from this view.
    """

    id: uuid.UUID
    name: str
    address: str
    owner_email: str
    owner_full_name: str
    latitude: float
    longitude: float
    is_verified: bool
    accepting_orders: bool
    rate_count: int
    created_at: datetime
    updated_at: datetime


class AdminShopListResponse(BaseModel):
    items: list[AdminShopResponse]
    next_cursor: str | None


class AdminActionResponse(BaseModel):
    """One entry of the moderation log."""

    id: int
    action: str
    shop_id: uuid.UUID
    shop_name: str
    admin_id: uuid.UUID | None
    admin_email: str | None
    reason: str | None
    at: datetime


class AdminActionListResponse(BaseModel):
    items: list[AdminActionResponse]
    next_cursor: str | None


class SuspendShopRequest(BaseModel):
    """Why a shop was taken offline. Required, so the log is useful later."""

    reason: str = Field(min_length=1, max_length=MAX_REASON_LENGTH)
