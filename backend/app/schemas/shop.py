import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.auth import UserResponse
from app.schemas.phone import Phone


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
    # How to reach the shop, when it has published a number.
    phone: str | None = None
    latitude: float
    longitude: float
    min_order_paise: int
    rates: list[RateItem]
    # How far away the shop is, in metres. Only the nearby search sets it.
    distance_m: int | None = None


class ShopListResponse(BaseModel):
    """The shops a customer can order from.

    `cash_at_store_enabled` is a platform setting, not a shop setting. It
    travels with the shop list because this is the response the order
    wizard already has when the customer reaches the payment step, and
    the customer should not be offered a way to pay that the server is
    going to refuse.
    """

    items: list[ShopResponse]
    next_cursor: str | None
    cash_at_store_enabled: bool = False


class VendorShopResponse(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    phone: str | None = None
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
    address: str | None = Field(default=None, min_length=1, max_length=300)
    phone: Phone | None = None
    min_order_paise: int | None = Field(default=None, ge=0)
    accepting_orders: bool | None = None
