"""Create PostGIS and citext extensions.

Revision ID: 0001
Revises:
Create Date: 2026-10-19

Downgrade drops citext only. PostGIS is database infrastructure that can
pre-exist (the official postgis Docker image installs it, together with
postgis_topology and postgis_tiger_geocoder, in the default database), so
it is deliberately left in place. Upgrade is idempotent either way.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS citext")
