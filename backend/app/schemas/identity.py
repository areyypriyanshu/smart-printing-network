import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.phone import Phone
from app.schemas.text import MultiLine, SingleLine


class OnboardingRequest(BaseModel):
    """What the person says they are here for.

    The address and the name are not in this body. They are read from
    the identity provider, because the provider is what proved them
    and what holds the address, and a body the browser filled in is
    not worth more than the browser that sent it.
    """

    role: Literal["customer", "vendor"]
    # The shop, for somebody who is here to run one. The fields are
    # only read when the role is a vendor, and a vendor without a shop
    # is refused.
    shop_name: SingleLine | None = Field(default=None, min_length=1, max_length=200)
    shop_address: MultiLine | None = Field(default=None, min_length=1, max_length=500)
    phone: Phone | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Literal["customer", "vendor", "admin"]
    created_at: datetime
