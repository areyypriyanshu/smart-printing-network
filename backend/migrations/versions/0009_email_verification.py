"""Prove that an email address belongs to the person who gave it.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-20

`users.email_verified` says whether the address has been proved. The
previous application version does not know the column and keeps
working: it never writes it, and the default is false, so every account
that existed before this migration is unverified.

`email_verification_tokens` holds the tokens that have been sent. Only
the hash of a token is stored, so a row that is read cannot be turned
into a link that verifies anything. A used token keeps its row, so a
link that is clicked twice is answered the same way both times, and the
answer does not depend on whether the row is still there.

The shape of this migration is expand only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "email_verification_tokens_user_idx",
        "email_verification_tokens",
        ["user_id"],
    )
    op.create_index(
        "email_verification_tokens_expiry_idx",
        "email_verification_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "email_verification_tokens_expiry_idx",
        table_name="email_verification_tokens",
    )
    op.drop_index(
        "email_verification_tokens_user_idx",
        table_name="email_verification_tokens",
    )
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "email_verified")
