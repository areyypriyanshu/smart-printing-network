"""The format an upload arrived in.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-20

`uploads.source_format` records what the customer actually uploaded. A
Word, Excel or PowerPoint file is converted to a PDF before it is
printed, and this says what it was before the conversion, so the file
the shop downloads can be named for what it is.

The shape of this migration is expand only. The previous application
version works against the new schema: it never writes this column, and
the new constraint only applies to rows that have it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_FORMATS = (
    "'pdf','docx','xlsx','pptx','legacy_office','rtf','image','text','empty','unknown'"
)


def upgrade() -> None:
    op.add_column("uploads", sa.Column("source_format", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_uploads_source_format",
        "uploads",
        f"source_format IS NULL OR source_format IN ({SOURCE_FORMATS})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_uploads_source_format", "uploads", type_="check")
    op.drop_column("uploads", "source_format")
