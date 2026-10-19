import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.auth import UserResponse


class RateItem(BaseModel):
    paper_size: Literal["A4", "A3"]
    color: bool
    duplex: bool
    rate_paise: int = Field(gt=0)


class RatesReplaceRequest(BaseModel):
    rates: list[RateItem] = Field(max_length=8)

    @model_validator(mode="after")
    def _reject_duplicate_combinations(self) -> Self:
        seen = {(item.paper_size, item.color, item.duplex) for item in self.rates}
        if len(seen) != len(self.rates):
            raise ValueError("duplicate paper_size/color/duplex combinations")
        return self


class ShopResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    latitude: float
    longitude: float
    min_order_paise: int
    rates: list[RateItem]


class ShopListResponse(BaseModel):
    items: list[ShopResponse]
    next_cursor: str | None


class VendorShopResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    latitude: float
    longitude: float
    min_order_paise: int
    is_verified: bool
    accepting_orders: bool
    created_at: datetime
    updated_at: datetime


class VendorRegistrationResponse(BaseModel):
    user: UserResponse
    shop: VendorShopResponse


class VendorShopUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    min_order_paise: int | None = Field(default=None, ge=0)
    accepting_orders: bool | None = None
