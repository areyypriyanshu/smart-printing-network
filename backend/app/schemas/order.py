import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.limits import MAX_COPIES


class OrderCreateRequest(BaseModel):
    upload_id: uuid.UUID
    shop_id: uuid.UUID
    paper_size: Literal["A4", "A3"]
    color: bool
    duplex: bool
    copies: int = Field(ge=1, le=MAX_COPIES)
    expected_price_paise: int | None = Field(default=None, ge=1)
    quality_acknowledged: bool = False


class OrderResponse(BaseModel):
    id: uuid.UUID
    order_no: int
    status: str
    status_reason: str | None
    shop_id: uuid.UUID
    upload_id: uuid.UUID
    page_count: int
    copies: int
    paper_size: str
    color: bool
    duplex: bool
    rate_paise: int
    min_order_paise: int
    price_paise: int
    pickup_code: str | None
    payment_method: str
    paid_at: datetime | None
    quality_acknowledged: bool
    created_at: datetime


class OrderEventResponse(BaseModel):
    from_status: str | None
    to_status: str
    actor_type: str
    reason: str | None
    at: datetime


class OrderCreateResponse(BaseModel):
    order: OrderResponse


class OrderDetailResponse(BaseModel):
    order: OrderResponse
    events: list[OrderEventResponse]
    # Whether the file is still stored, and so whether the job can be
    # printed again without uploading it a second time.
    file_available: bool = False


class ReorderResponse(BaseModel):
    """What is needed to print the same job again.

    The upload is a copy of the original file, with its own retention
    window, so the two orders never share a file.
    """

    upload_id: uuid.UUID
    paper_size: str
    color: bool
    duplex: bool
    copies: int
    shop_id: uuid.UUID


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    next_cursor: int | None


class FileUrlResponse(BaseModel):
    """A short-lived presigned download link for a stored PDF."""

    url: str
    expires_in_seconds: int
    filename: str
