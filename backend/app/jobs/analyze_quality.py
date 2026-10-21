"""The job that analyses the files customers have asked about.

The analysis is CPU heavy, so it happens here and not in the request
that asked for it. The job claims the reports that are waiting, one at a
time, and each report is locked while it is being worked on, so two
workers running at the same time do not analyse the same file twice.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gateways.storage import Storage
from app.models import QualityReport
from app.services.quality_service import run_one

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
            .where(QualityReport.status == "PENDING")
            .order_by(QualityReport.created_at.asc())
            .limit(BATCH_SIZE)
        )
    )
    analysed = 0
    for report_id in report_ids:
        if run_one(session, report_id=report_id, storage=storage, now=now):
            analysed += 1
    return analysed
