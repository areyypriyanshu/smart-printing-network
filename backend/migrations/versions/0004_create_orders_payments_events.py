"""Create orders, order events, payments and webhook events.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_STATUS_SQL = "status IN ('PAID','ACCEPTED','PRINTING','READY')"


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("order_no", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'PENDING_PAYMENT'"),
            nullable=False,
        ),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("paper_size", sa.Text(), nullable=False),
        sa.Column("color", sa.Boolean(), nullable=False),
        sa.Column("duplex", sa.Boolean(), nullable=False),
        sa.Column("copies", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("rate_paise", sa.Integer(), nullable=False),
        sa.Column("min_order_paise", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("pickup_code", sa.CHAR(length=6), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING_PAYMENT','PAID','ACCEPTED','PRINTING','READY',"
            "'COLLECTED','REJECTED','CANCELLED','EXPIRED')",
            name="ck_orders_status",
        ),
        sa.CheckConstraint("paper_size IN ('A4','A3')", name="ck_orders_paper_size"),
        sa.CheckConstraint("copies BETWEEN 1 AND 100", name="ck_orders_copies"),
        sa.CheckConstraint("page_count > 0", name="ck_orders_page_count"),
        sa.CheckConstraint("rate_paise > 0", name="ck_orders_rate_paise"),
        sa.CheckConstraint("min_order_paise >= 0", name="ck_orders_min_order_paise"),
        sa.CheckConstraint("price_paise > 0", name="ck_orders_price_paise"),
        sa.CheckConstraint(
            "price_paise = GREATEST(page_count * copies * rate_paise, min_order_paise)",
            name="ck_orders_price_formula",
        ),
        sa.CheckConstraint(
            "pickup_code IS NULL OR pickup_code ~ '^[0-9]{6}$'",
            name="ck_orders_pickup_code",
        ),
        sa.CheckConstraint(
            "status NOT IN ('PAID','ACCEPTED','PRINTING','READY','COLLECTED') "
            "OR (paid_at IS NOT NULL AND pickup_code IS NOT NULL)",
            name="ck_orders_paid_has_code",
        ),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR paid_at IS NOT NULL",
            name="ck_orders_rejected_paid",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"]),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_no"),
        sa.UniqueConstraint("upload_id", name="uq_orders_upload_id"),
        sa.UniqueConstraint("customer_id", "idempotency_key", name="uq_orders_idempotency"),
    )
    op.create_index("orders_customer_idx", "orders", ["customer_id", sa.text("created_at DESC")])
    op.create_index(
        "orders_queue_idx",
        "orders",
        ["shop_id", "status", "paid_at"],
        postgresql_where=sa.text(ACTIVE_STATUS_SQL),
    )
    op.create_index(
        "orders_pending_expiry_idx",
        "orders",
        ["created_at"],
        postgresql_where=sa.text("status = 'PENDING_PAYMENT'"),
    )
    op.create_index(
        "orders_unaccepted_idx",
        "orders",
        ["paid_at"],
        postgresql_where=sa.text("status = 'PAID'"),
    )

    op.create_table(
        "order_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('customer','vendor','system','webhook')",
            name="ck_order_events_actor_type",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("order_events_order_idx", "order_events", ["order_id", "at"])
    op.create_index("order_events_status_idx", "order_events", ["to_status", "at"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_order_id", sa.Text(), nullable=False),
        sa.Column("provider_payment_id", sa.Text(), nullable=True),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default=sa.text("'INR'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'CREATED'"), nullable=False),
        sa.Column("refund_id", sa.Text(), nullable=True),
        sa.Column("refund_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("refund_next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("provider IN ('razorpay','fake')", name="ck_payments_provider"),
        sa.CheckConstraint("amount_paise > 0", name="ck_payments_amount_paise"),
        sa.CheckConstraint("currency = 'INR'", name="ck_payments_currency"),
        sa.CheckConstraint(
            "status IN ('CREATED','CAPTURED','FAILED','REFUND_PENDING','REFUNDED')",
            name="ck_payments_status",
        ),
        sa.CheckConstraint("refund_attempts >= 0", name="ck_payments_refund_attempts"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
        sa.UniqueConstraint("provider_order_id"),
        sa.UniqueConstraint("provider_payment_id"),
        sa.UniqueConstraint("refund_id"),
    )
    op.create_index(
        "payments_refund_idx",
        "payments",
        ["refund_next_attempt_at"],
        postgresql_where=sa.text("status = 'REFUND_PENDING'"),
    )

    op.create_table(
        "webhook_events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_index("payments_refund_idx", table_name="payments")
    op.drop_table("payments")
    op.drop_index("order_events_status_idx", table_name="order_events")
    op.drop_index("order_events_order_idx", table_name="order_events")
    op.drop_table("order_events")
    op.drop_index("orders_unaccepted_idx", table_name="orders")
    op.drop_index("orders_pending_expiry_idx", table_name="orders")
    op.drop_index("orders_queue_idx", table_name="orders")
    op.drop_index("orders_customer_idx", table_name="orders")
    op.drop_table("orders")
