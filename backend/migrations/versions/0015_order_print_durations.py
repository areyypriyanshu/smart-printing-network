"""Expose print durations from the existing order event history.

The view is additive and reversible. It reads no uploaded file and stores no
new data. READY, rather than COLLECTED, completes the print measurement.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW order_print_durations AS
        SELECT
            o.id AS order_id,
            o.shop_id,
            (o.page_count * o.copies) AS print_units,
            EXTRACT(EPOCH FROM (ready.at - printing.at)) / 60.0 AS print_minutes,
            ready.at AS completed_at,
            ready.id AS ready_event_id
        FROM orders o
        JOIN LATERAL (
            SELECT e.at
            FROM order_events e
            WHERE e.order_id = o.id AND e.to_status = 'PRINTING'
            ORDER BY e.at, e.id
            LIMIT 1
        ) printing ON true
        JOIN LATERAL (
            SELECT e.at, e.id
            FROM order_events e
            WHERE e.order_id = o.id AND e.to_status = 'READY'
            ORDER BY e.at, e.id
            LIMIT 1
        ) ready ON true
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW order_print_durations")
