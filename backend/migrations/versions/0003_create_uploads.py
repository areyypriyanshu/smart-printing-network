"""Create uploads table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("file_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("page_count > 0", name="ck_uploads_page_count"),
        sa.CheckConstraint("size_bytes > 0", name="ck_uploads_size_bytes"),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_key"),
    )
    op.create_index(
        "uploads_customer_idx",
        "uploads",
        ["customer_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "uploads_purge_idx",
        "uploads",
        ["delete_after"],
        postgresql_where=sa.text("file_deleted_at IS NULL AND delete_after IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uploads_purge_idx", table_name="uploads")
    op.drop_index("uploads_customer_idx", table_name="uploads")
    op.drop_table("uploads")
