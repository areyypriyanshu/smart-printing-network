import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.identity import UserResponse
from app.schemas.phone import Phone
from app.schemas.text import MultiLine, SingleLine


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
    # What has to be shown to a person when this shop's place on the map
    # is shown to them. OpenStreetMap asks for it.
    attribution: str | None = None


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
    # What has to be shown to a person when the data here is shown to
    # them. OpenStreetMap asks for it.
    attribution: str | None = None


class ShopSearchQuery(BaseModel):
    """What the customer is asking the search for.

    The parts come in groups, and a group is either there or it is not.
    A point without a longitude is not a place, and a paper size
    without a file is not a price, so the query refuses both rather
    than guessing what was meant.
    """

    # Where the customer is, either as a point or as an address that is
    # looked up. A point is more precise, so it wins when both are
    # given.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = Field(default=None, max_length=300)
    # How far the customer is willing to travel, in metres.
    radius_m: int = Field(default=5000, ge=100, le=50000)
    # "distance" needs a point, "price" needs a file and the options.
    # Without either, the order is the server's to choose.
    sort: Literal["distance", "price"] | None = None
    # The file the prices are for, and the options it would be printed
    # with.
    upload_id: uuid.UUID | None = None
    paper_size: Literal["A4", "A3"] | None = None
    color: bool | None = None
    duplex: bool | None = None
    copies: int | None = Field(default=None, ge=1, le=100)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _the_parts_go_together(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("a latitude and a longitude go together")
        chosen = (self.paper_size, self.color, self.duplex, self.copies)
        if any(part is not None for part in chosen) and not all(
            part is not None for part in chosen
        ):
            raise ValueError("the paper size, the colour, the sides and the copies go together")
        if self.upload_id is None and self.paper_size is not None:
            raise ValueError("a file is needed before a price can be shown")
        if self.upload_id is not None and self.paper_size is None:
            raise ValueError("the print options are needed before a price can be shown")
        return self

    @property
    def wants_prices(self) -> bool:
        """Whether the customer asked for a price for a file."""
        return self.upload_id is not None and self.paper_size is not None


class ShopSearchItem(BaseModel):
    """One shop in the result of a search.

    The price is the price the customer would be charged for this file
    with these options. It comes from the same function the order flow
    uses, so what is shown here is what is charged.
    """

    id: uuid.UUID
    name: str
    address: str
    phone: str | None = None
    latitude: float
    longitude: float
    min_order_paise: int
    # How far away the shop is, in metres. It is absent when the
    # customer did not say where they are.
    distance_m: int | None = None
    # What it would cost, and what that is per page. Both are absent
    # when the customer did not ask for prices.
    price_paise: int | None = None
    rate_paise: int | None = None


class ShopSearchResponse(BaseModel):
    """The shops the search found."""

    items: list[ShopSearchItem]
    # What has to be shown to a person when the data here is shown to
    # them. OpenStreetMap asks for it.
    attribution: str | None = None


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
    name: SingleLine | None = Field(default=None, min_length=1, max_length=200)
    address: MultiLine | None = Field(default=None, min_length=1, max_length=300)
    phone: Phone | None = None
    min_order_paise: int | None = Field(default=None, ge=0)
    accepting_orders: bool | None = None
