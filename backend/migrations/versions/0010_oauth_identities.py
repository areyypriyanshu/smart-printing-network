"""Remember the accounts that sign in with a provider.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-20

An OAuth identity is the account at the provider: the provider and the
identifier it gave. The identifier is not the email address, because
the address at a provider can change and the account cannot, and
because the address is what two platforms argue about.

The provider and the identifier together are unique, so one account at
a provider is one identity here, and an identity is one account here.
There is no unique constraint on the user, because an account may have
more than one identity: a customer who signs in with a password and
also connects Google has both.

The shape of this migration is expand only. The previous application
version does not know the table and keeps working: it never writes it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("oauth_identities_user_idx", table_name="oauth_identities")
    op.drop_table("oauth_identities")
