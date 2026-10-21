"""Remove the table that remembered the accounts that sign in with a provider.

Revision ID: 0013
Revises: 0012

The sign in with Google that this table served is gone. The identity
provider owns that now, and it keeps its own record of which account at
a provider belongs to which person, so the copy here had nothing left
to do.

The table is empty in every deployment that has run, because the sign
in it served was never configured, so nothing is lost. The migration is
reversible anyway: the downgrade puts the table back with the same
shape.

The `users.has_password` column stays. It was added for the same
feature, but it marks an account that has no usable local password,
which is also what an account the identity provider provisions looks
like, so it keeps its job until the local password machinery is
removed in the contraction phase. Removing it here would also break a
rollback, because the previous application version selects it on every
request.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("oauth_identities_user_idx", table_name="oauth_identities")
    op.drop_table("oauth_identities")


def downgrade() -> None:
    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_subject", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_subject"),
    )
    op.create_index("oauth_identities_user_idx", "oauth_identities", ["user_id"])
