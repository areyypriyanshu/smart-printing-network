import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ACTIVE_STATUS_SQL = "status IN ('PAID','ACCEPTED','PRINTING','READY')"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING_PAYMENT','PAID','ACCEPTED','PRINTING','READY',"
            "'COLLECTED','REJECTED','CANCELLED','EXPIRED')",
            name="ck_orders_status",
        ),
        CheckConstraint("paper_size IN ('A4','A3')", name="ck_orders_paper_size"),
        CheckConstraint("copies BETWEEN 1 AND 100", name="ck_orders_copies"),
        CheckConstraint("page_count > 0", name="ck_orders_page_count"),
        CheckConstraint("rate_paise > 0", name="ck_orders_rate_paise"),
        CheckConstraint("min_order_paise >= 0", name="ck_orders_min_order_paise"),
        CheckConstraint("price_paise > 0", name="ck_orders_price_paise"),
        CheckConstraint(
            "price_paise = GREATEST(page_count * copies * rate_paise, min_order_paise)",
            name="ck_orders_price_formula",
        ),
        CheckConstraint(
            "pickup_code IS NULL OR pickup_code ~ '^[0-9]{6}$'",
            name="ck_orders_pickup_code",
        ),
        CheckConstraint(
            "status NOT IN ('PAID','ACCEPTED','PRINTING','READY','COLLECTED') "
            "OR (paid_at IS NOT NULL AND pickup_code IS NOT NULL)",
            name="ck_orders_paid_has_code",
        ),
        CheckConstraint(
            "status <> 'REJECTED' OR paid_at IS NOT NULL",
            name="ck_orders_rejected_paid",
        ),
        UniqueConstraint("upload_id", name="uq_orders_upload_id"),
        UniqueConstraint("customer_id", "idempotency_key", name="uq_orders_idempotency"),
        Index("orders_customer_idx", "customer_id", text("created_at DESC")),
        Index(
            "orders_queue_idx",
            "shop_id",
            "status",
            "paid_at",
            postgresql_where=text(ACTIVE_STATUS_SQL),
        ),
        Index(
            "orders_pending_expiry_idx",
            "created_at",
            postgresql_where=text("status = 'PENDING_PAYMENT'"),
        ),
        Index(
            "orders_unaccepted_idx",
            "paid_at",
            postgresql_where=text("status = 'PAID'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    order_no: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shops.id"))
    upload_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("uploads.id"))
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'PENDING_PAYMENT'")
    )
    status_reason: Mapped[str | None] = mapped_column(Text)
    paper_size: Mapped[str] = mapped_column(Text)
    color: Mapped[bool] = mapped_column(Boolean)
    duplex: Mapped[bool] = mapped_column(Boolean)
    copies: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer)
    rate_paise: Mapped[int] = mapped_column(Integer)
    min_order_paise: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    price_paise: Mapped[int] = mapped_column(Integer)
    pickup_code: Mapped[str | None] = mapped_column(CHAR(6))
    idempotency_key: Mapped[str] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('customer','vendor','system','webhook')",
            name="ck_order_events_actor_type",
        ),
        Index("order_events_order_idx", "order_id", "at"),
        Index("order_events_status_idx", "to_status", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"))
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("provider IN ('razorpay','fake')", name="ck_payments_provider"),
        CheckConstraint("amount_paise > 0", name="ck_payments_amount_paise"),
        CheckConstraint("currency = 'INR'", name="ck_payments_currency"),
        CheckConstraint(
            "status IN ('CREATED','CAPTURED','FAILED','REFUND_PENDING','REFUNDED')",
            name="ck_payments_status",
        ),
        CheckConstraint("refund_attempts >= 0", name="ck_payments_refund_attempts"),
        Index(
            "payments_refund_idx",
            "refund_next_attempt_at",
            postgresql_where=text("status = 'REFUND_PENDING'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("orders.id"), unique=True)
    provider: Mapped[str] = mapped_column(Text)
    provider_order_id: Mapped[str] = mapped_column(Text, unique=True)
    provider_payment_id: Mapped[str | None] = mapped_column(Text, unique=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(CHAR(3), server_default=text("'INR'"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'CREATED'"))
    refund_id: Mapped[str | None] = mapped_column(Text, unique=True)
    refund_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    refund_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
