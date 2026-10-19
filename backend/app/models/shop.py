import uuid
from datetime import datetime

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint("min_order_paise >= 0", name="ck_shops_min_order_paise"),
        CheckConstraint(
            "phone IS NULL OR ("
            "phone ~ '^[0-9+() .-]{7,25}$' AND "
            "length(regexp_replace(phone, '[^0-9]', '', 'g')) BETWEEN 7 AND 15"
            ")",
            name="ck_shops_phone",
        ),
        Index("shops_location_gix", "location", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    # How a customer reaches the shop. Optional, and editable afterwards.
    phone: Mapped[str | None] = mapped_column(Text)
    location: Mapped[WKBElement] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )
    min_order_paise: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    accepting_orders: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ShopRate(Base):
    __tablename__ = "shop_rates"
    __table_args__ = (
        CheckConstraint("paper_size IN ('A4','A3')", name="ck_shop_rates_paper_size"),
        CheckConstraint("rate_paise > 0", name="ck_shop_rates_rate_paise"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shops.id"), primary_key=True)
    paper_size: Mapped[str] = mapped_column(Text, primary_key=True)
    color: Mapped[bool] = mapped_column(Boolean, primary_key=True)
    duplex: Mapped[bool] = mapped_column(Boolean, primary_key=True)
    rate_paise: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
