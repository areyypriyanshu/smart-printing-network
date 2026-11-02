"""Keep the newest Clerk profile when webhook deliveries race.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str | None = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("clerk_profile_updated_at", sa.BigInteger(), nullable=True))
    op.add_column(
        "users", sa.Column("clerk_profile_event_timestamp", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "clerk_profile_event_timestamp")
    op.drop_column("users", "clerk_profile_updated_at")
