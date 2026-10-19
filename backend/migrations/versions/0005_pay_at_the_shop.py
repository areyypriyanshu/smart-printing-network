"""Pay at the shop: a second payment method on the same order.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-19

An order can now be paid in cash at the counter instead of online. The
order is booked as RESERVED, the shop works it like any other job, and the
money changes hands when the customer collects it.

The shape of this migration is expand only. The previous application
version keeps working against the new schema: it inserts orders with
`payment_method` defaulting to 'online', and the constraints that changed
say exactly the same thing for an online order as they did before.

Two things are worth stating plainly.

`reserved_at` is backfilled from `paid_at` for the orders that already
exist. It is the queue order and the auto reject cutoff for both methods,
so an online order that was paid before this migration keeps its place in
the shop's queue and keeps its auto reject deadline.

Rolling the schema back while cash orders exist is refused. The old
`ck_orders_status` has no RESERVED, so the rows could not be written back.
Resolve or cancel the cash orders first, then roll back.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_STATUS_SQL = "status IN ('PAID','RESERVED','ACCEPTED','PRINTING','READY')"

OLD_STATUS_CHECK = (
    "status IN ('PENDING_PAYMENT','PAID','ACCEPTED','PRINTING','READY',"
    "'COLLECTED','REJECTED','CANCELLED','EXPIRED')"
)
NEW_STATUS_CHECK = (
    "status IN ('PENDING_PAYMENT','PAID','RESERVED','ACCEPTED','PRINTING','READY',"
    "'COLLECTED','REJECTED','CANCELLED','EXPIRED')"
)

OLD_PAID_HAS_CODE = (
    "status NOT IN ('PAID','ACCEPTED','PRINTING','READY','COLLECTED') "
    "OR (paid_at IS NOT NULL AND pickup_code IS NOT NULL)"
)
NEW_PAID_HAS_CODE = (
    "NOT ("
    "payment_method = 'online'"
    " AND status IN ('PAID','ACCEPTED','PRINTING','READY','COLLECTED')"
    " AND (paid_at IS NULL OR pickup_code IS NULL)"
    ")"
)
NEW_CASH_HAS_CODE = (
    "NOT ("
    "payment_method = 'at_store'"
    " AND status IN ('RESERVED','ACCEPTED','PRINTING','READY')"
    " AND pickup_code IS NULL"
    ")"
)
NEW_CASH_COLLECTED_PAID = (
    "NOT ("
    "payment_method = 'at_store'"
    " AND status = 'COLLECTED'"
    " AND (paid_at IS NULL OR pickup_code IS NULL)"
    ")"
)

OLD_REJECTED_PAID = "status <> 'REJECTED' OR paid_at IS NOT NULL"
NEW_REJECTED_PAID = (
    "NOT (payment_method = 'online' AND status = 'REJECTED' AND paid_at IS NULL)"
)

OLD_PROVIDER_CHECK = "provider IN ('razorpay','fake')"
NEW_PROVIDER_CHECK = "provider IN ('razorpay','fake','cash')"
NEW_CASH_NOT_REFUNDED = "NOT (provider = 'cash' AND status = 'REFUND_PENDING')"


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "payment_method",
            sa.Text(),
            server_default=sa.text("'online'"),
            nullable=False,
        ),
    )
    op.add_column("orders", sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_orders_payment_method",
        "orders",
        "payment_method IN ('online','at_store')",
    )

    # The orders that already exist were paid online. Their queue place
    # and their auto reject deadline are the time they were paid, so that
    # is what `reserved_at` gets.
    op.execute("UPDATE orders SET reserved_at = paid_at WHERE paid_at IS NOT NULL")

    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint("ck_orders_status", "orders", NEW_STATUS_CHECK)

    op.drop_constraint("ck_orders_paid_has_code", "orders", type_="check")
    op.create_check_constraint("ck_orders_paid_has_code", "orders", NEW_PAID_HAS_CODE)
    op.create_check_constraint("ck_orders_cash_has_code", "orders", NEW_CASH_HAS_CODE)
    op.create_check_constraint(
        "ck_orders_cash_collected_paid", "orders", NEW_CASH_COLLECTED_PAID
    )

    op.drop_constraint("ck_orders_rejected_paid", "orders", type_="check")
    op.create_check_constraint("ck_orders_rejected_paid", "orders", NEW_REJECTED_PAID)

    op.drop_constraint("ck_payments_provider", "payments", type_="check")
    op.create_check_constraint("ck_payments_provider", "payments", NEW_PROVIDER_CHECK)
    op.create_check_constraint(
        "ck_payments_cash_not_refunded", "payments", NEW_CASH_NOT_REFUNDED
    )

    op.drop_index("orders_queue_idx", table_name="orders")
    op.create_index(
        "orders_queue_idx",
        "orders",
        ["shop_id", "status", "reserved_at"],
        postgresql_where=sa.text(ACTIVE_STATUS_SQL),
    )

    op.drop_index("orders_unaccepted_idx", table_name="orders")
    op.create_index(
        "orders_unaccepted_idx",
        "orders",
        ["reserved_at"],
        postgresql_where=sa.text("status IN ('PAID','RESERVED')"),
    )

    op.create_index(
        "orders_no_show_idx",
        "orders",
        ["ready_at"],
        postgresql_where=sa.text("status = 'READY'"),
    )


def downgrade() -> None:
    reserved = op.get_bind().execute(
        sa.text("SELECT count(*) FROM orders WHERE status = 'RESERVED'")
    ).scalar()
    if reserved:
        raise RuntimeError(
            "There are RESERVED orders, and the previous schema has no RESERVED "
            "status. Cancel or collect them before rolling the schema back."
        )

    op.drop_index("orders_no_show_idx", table_name="orders")

    op.drop_index("orders_unaccepted_idx", table_name="orders")
    op.create_index(
        "orders_unaccepted_idx",
        "orders",
        ["paid_at"],
        postgresql_where=sa.text("status = 'PAID'"),
    )

    op.drop_index("orders_queue_idx", table_name="orders")
    op.create_index(
        "orders_queue_idx",
        "orders",
        ["shop_id", "status", "paid_at"],
        postgresql_where=sa.text("status IN ('PAID','ACCEPTED','PRINTING','READY')"),
    )

    op.drop_constraint("ck_payments_cash_not_refunded", "payments", type_="check")
    op.drop_constraint("ck_payments_provider", "payments", type_="check")
    op.create_check_constraint("ck_payments_provider", "payments", OLD_PROVIDER_CHECK)

    op.drop_constraint("ck_orders_rejected_paid", "orders", type_="check")
    op.create_check_constraint("ck_orders_rejected_paid", "orders", OLD_REJECTED_PAID)

    op.drop_constraint("ck_orders_cash_collected_paid", "orders", type_="check")
    op.drop_constraint("ck_orders_cash_has_code", "orders", type_="check")
    op.drop_constraint("ck_orders_paid_has_code", "orders", type_="check")
    op.create_check_constraint("ck_orders_paid_has_code", "orders", OLD_PAID_HAS_CODE)

    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint("ck_orders_status", "orders", OLD_STATUS_CHECK)

    op.drop_constraint("ck_orders_payment_method", "orders", type_="check")
    op.drop_column("orders", "ready_at")
    op.drop_column("orders", "reserved_at")
    op.drop_column("orders", "payment_method")
