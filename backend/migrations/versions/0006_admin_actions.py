"""The admin audit trail: who approved or suspended a shop.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24

Shops are the one thing in this product that a person outside the system
decides about, so "who approved this shop" has to have an answer. This
table records it.

The shape is a plain additive create. The previous application version
keeps working against the new schema, because it never writes to this
table and nothing about the existing tables changes. The `admin_id` column
is nullable on purpose: a shop approved from the command line by the
operator has no admin account behind it, and forcing one would mean
inventing a user for a shell command.

The action column is a text column with a check constraint rather than a
Postgres enum, for the reason given in ADR 005: adding a value to an
enum cannot be done without a lock that blocks reads.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('shop_approved','shop_suspended')",
            name="ck_admin_actions_action",
        ),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "admin_actions_shop_idx",
        "admin_actions",
        ["shop_id", "at"],
        unique=False,
    )
    op.create_index(
        "admin_actions_admin_idx",
        "admin_actions",
        ["admin_id", "at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("admin_actions_admin_idx", table_name="admin_actions")
    op.drop_index("admin_actions_shop_idx", table_name="admin_actions")
    op.drop_table("admin_actions")
