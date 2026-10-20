import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.schemas.email import Email
from app.schemas.phone import Phone
from app.schemas.text import MultiLine, SingleLine
from app.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, validate_password_strength

#: The password policy, shared with the operator CLI, so the two paths
#: cannot drift apart.
Password = Annotated[str, AfterValidator(validate_password_strength)]


class RegisterRequest(BaseModel):
    email: Email
    password: Password = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    full_name: SingleLine = Field(min_length=1, max_length=200)


class RegisterVendorRequest(RegisterRequest):
    shop_name: SingleLine = Field(min_length=1, max_length=200)
    shop_address: MultiLine = Field(min_length=1, max_length=500)
    # How a customer reaches the shop. Optional: a shop that would rather
    # not publish a number can leave it out and add one later.
    phone: Phone | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Literal["customer", "vendor", "admin"]
    created_at: datetime


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
