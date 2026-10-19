import uuid
from typing import Literal

from pydantic import BaseModel, Field


class QuoteRequest(BaseModel):
    upload_id: uuid.UUID
    shop_id: uuid.UUID
    paper_size: Literal["A4", "A3"]
    color: bool
    duplex: bool
    copies: int = Field(ge=1, le=100)


class QuoteResponse(BaseModel):
    upload_id: uuid.UUID
    shop_id: uuid.UUID
    page_count: int
    copies: int
    rate_paise: int
    min_order_paise: int
    price_paise: int
