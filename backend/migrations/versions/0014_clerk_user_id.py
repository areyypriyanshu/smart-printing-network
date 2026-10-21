"""Add the identity provider's identifier to the accounts.

The account is now found by the identifier the provider's session token
names, rather than by a row this application minted itself. The column
is nullable, because an account that has not signed in yet has no
identifier, and unique, because one person has one account.

The password column becomes nullable in the same migration, because an
account the provider provisions has no password and there is nowhere
else for it to come from. The column itself is left in place: the
version of the application that is running now does not read it, and
dropping it is a separate change that can be made once no deployed
version needs it. That order is the same one the deployment notes
describe, where a rollback is a redeploy of the previous image.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str | None = "0014"
down_revision: str | None = "0013"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("clerk_user_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "users_clerk_user_id_key",
        "users",
        ["clerk_user_id"],
        unique=True,
    )
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    # A row without a password cannot be given one, so the column is
    # filled with a value that cannot be used to sign in before it is
    # made not null again. The string is an argon2 hash of nothing, so
    # it never matches a password.
    op.execute(
        "UPDATE users SET password_hash = "
        "'$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzb21lc2FsdA$' "
        "WHERE password_hash IS NULL"
    )
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=False)
    op.drop_index("users_clerk_user_id_key", table_name="users")
    op.drop_column("users", "clerk_user_id")
