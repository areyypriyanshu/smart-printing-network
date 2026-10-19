import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ACTIONS = ("shop_approved", "shop_suspended")


class AdminAction(Base):
    """A moderation action on a shop.

    "Who approved this shop" has to have an answer. Shops are the one
    thing in this product that a person outside the system decides about,
    and a student who has a bad experience at an approved shop needs
    somewhere to point.

    `admin_id` is null when the action was taken from the command line by
    the operator rather than from the web panel. The CLI is how a server
    with no admin account set up yet is still run, and the null says "this
    was done by whoever holds the server".

    The primary key is a sequence rather than a UUID, for the same reason
    `order_events` uses one. The log is read in order, and `now()` is the
    time the transaction started, so two actions taken in the same
    transaction carry the same timestamp. A sequence gives the tie a
    deterministic answer, so the newest action really is the newest one.
    """

    __tablename__ = "admin_actions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('shop_approved','shop_suspended')",
            name="ck_admin_actions_action",
        ),
        Index("admin_actions_shop_idx", "shop_id", "at"),
        Index("admin_actions_admin_idx", "admin_id", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, primary_key=True)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shops.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
