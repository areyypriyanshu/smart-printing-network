import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
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
    # The three columns below are the remains of the local
    # authentication. Nothing writes them and nothing reads them: the
    # provider holds the password and proves the address. They are still
    # here because the deployment runs the migrations before the new
    # image starts and a rollback is a redeploy of the previous image,
    # which still reads them. They go in the contraction, on their own.
    password_hash: Mapped[str | None] = mapped_column(Text)
    # Whether the account has a usable local password. It is a leftover
    # of the same thing and it says the same thing.
    has_password: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Whether the address has been proved. The provider decides, and
    # nothing here acts on the answer.
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RefreshToken(Base):
    """A session that the local authentication issued.

    Nothing writes this table and nothing reads it. It is the remains of
    the local sign in, and it is still here because the previous image
    reads it and a rollback is a redeploy of that image.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("refresh_tokens_user_idx", "user_id"),
        Index("refresh_tokens_family_idx", "family_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailVerificationToken(Base):
    """A token that was sent to an address to prove it belongs to its owner.

    Only the hash of the token is kept, so a row that is read from the
    database cannot be turned into a link that verifies anything. A used
    token keeps its row, so a link that is clicked twice is answered the
    same way both times.
    """

    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        Index("email_verification_tokens_user_idx", "user_id"),
        Index("email_verification_tokens_expiry_idx", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
