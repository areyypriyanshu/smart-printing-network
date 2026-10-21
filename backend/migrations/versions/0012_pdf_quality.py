"""Add advisory PDF quality reports.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "quality_acknowledged",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_table(
        "quality_reports",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column("pages", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("summary", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column(
            "acknowledged", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("algorithm_version", sa.Text(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','DONE','FAILED')",
            name="ck_quality_reports_status",
        ),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_id"),
    )
    op.create_index(
        "quality_reports_status_idx",
        "quality_reports",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("quality_reports_status_idx", table_name="quality_reports")
    op.drop_table("quality_reports")
    op.drop_column("orders", "quality_acknowledged")
