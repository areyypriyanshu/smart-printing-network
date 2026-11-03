import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ROLES = ("customer", "vendor", "admin")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('customer','vendor','admin')", name="ck_users_role"),
        # The index is named the way the migration named it, so the two
        # agree. A unique constraint and a unique index are the same
        # rule and different objects, and the schema check compares the
        # objects.
        Index("users_clerk_user_id_key", "clerk_user_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    # The identity provider's own identifier for this person. It is
    # what the session token names, and it is the only thing that links
    # a local account to the provider. It is null for an account that
    # has not been through the sign in yet, and unique, because one
    # person has one account.
    clerk_user_id: Mapped[str | None] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Whether the provider has proved the address. Signed provider
    # updates keep this local copy current; uploads and orders require it.
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Clerk webhooks can arrive out of order. These provider timestamps
    # let a later transaction reject a profile read that is older than
    # the one already applied.
    clerk_profile_updated_at: Mapped[int | None] = mapped_column(BigInteger)
    clerk_profile_event_timestamp: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
