"""The job that analyses the files customers have asked about.

The analysis is CPU heavy, so it happens here and not in the request
that asked for it. The job selects waiting reports in small locked
batches, then rechecks and claims each report under its own lock before
work starts. This prevents an earlier commit from releasing the other
batch locks and letting two workers analyse the same report.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.gateways.storage import Storage
from app.models import QualityReport
from app.services.quality_service import RECOVERY_TIMEOUT_SECONDS, run_one

logger = logging.getLogger(__name__)

#: How many reports one run of the job takes on. A small number, because
#: one file can take a while and the worker also has four other jobs.
BATCH_SIZE = 5


def run(session: Session, *, storage: Storage, now: datetime) -> int:
    """Analyse the reports that are waiting.

    Returns how many were analysed. Safe to run twice: a report that is
    done is not done again.
    """
    report_ids = list(
        session.scalars(
            select(QualityReport.id)
            .where(
                or_(
                    QualityReport.status == "PENDING",
                    and_(
                        QualityReport.status == "RUNNING",
                        or_(
                            QualityReport.started_at.is_(None),
                            QualityReport.started_at
                            <= now - timedelta(seconds=RECOVERY_TIMEOUT_SECONDS),
                        ),
                    ),
                )
            )
            .order_by(QualityReport.created_at.asc())
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )
    analysed = 0
    for report_id in report_ids:
        if run_one(session, report_id=report_id, storage=storage, now=now):
            analysed += 1
    return analysed
