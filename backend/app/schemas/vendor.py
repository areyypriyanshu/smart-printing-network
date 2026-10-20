import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.order import OrderEventResponse
from app.schemas.text import MultiLine

MAX_REASON_LENGTH = 500


class VendorOrderResponse(BaseModel):
    """An order as the shop sees it.

    Deliberately has no `pickup_code` field. The pickup code proves the
    customer collected the right order, so it must never be readable by the
    shop; the shop only ever receives it from the customer at the counter.
    """

    id: uuid.UUID
    order_no: int
    status: str
    status_reason: str | None
    upload_id: uuid.UUID
    page_count: int
    copies: int
    paper_size: str
    color: bool
    duplex: bool
    price_paise: int
    # The shop needs to know whether to expect the money online or in cash
    # at the counter.
    payment_method: str
    # When the order entered the shop's queue. The board counts down to
    # the auto reject from this, and a cash order has no paid_at to count
    # from until it is collected.
    reserved_at: datetime | None
    paid_at: datetime | None
    created_at: datetime


class VendorQueueResponse(BaseModel):
    """Active orders for one shop, oldest reservation first.

    `accept_timeout_minutes` is the server's own setting, sent so the board
    can warn about orders that are about to be auto rejected without the
    frontend keeping a second copy of the number.
    """

    items: list[VendorOrderResponse]
    accept_timeout_minutes: int


class VendorOrderDetailResponse(BaseModel):
    order: VendorOrderResponse
    events: list[OrderEventResponse]
    file_available: bool


class ReasonRequest(BaseModel):
    """A rejection or cancellation reason. Required by the PRD."""

    reason: MultiLine = Field(min_length=1, max_length=MAX_REASON_LENGTH)


class CollectRequest(BaseModel):
    """The pickup code the customer shows at the counter."""

    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")
