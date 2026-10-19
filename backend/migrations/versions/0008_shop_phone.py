"""A phone number for a shop.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20

`shops.phone` is how a customer reaches the shop that is printing their
project. It is nullable, because a shop may not want to publish a number,
and it is editable afterwards, so a shop that starts without one can add
it later.

The shape of this migration is expand only. The previous application
version works against the new schema: it never writes this column, and
the new constraint only applies to rows that have it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A phone number is free text with digits in it: spaces, dashes, brackets
# and a leading plus are all allowed. The digit count is what matters,
# and it is the same rule the request schema applies.
PHONE_CHECK = (
    "phone IS NULL OR ("
    "phone ~ '^[0-9+() .-]{7,25}$' AND "
    "length(regexp_replace(phone, '[^0-9]', '', 'g')) BETWEEN 7 AND 15"
    ")"
)


def upgrade() -> None:
    op.add_column("shops", sa.Column("phone", sa.Text(), nullable=True))
    op.create_check_constraint("ck_shops_phone", "shops", PHONE_CHECK)


def downgrade() -> None:
    op.drop_constraint("ck_shops_phone", "shops", type_="check")
    op.drop_column("shops", "phone")
