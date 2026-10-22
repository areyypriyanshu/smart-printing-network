"""The service behind the quality report.

The report is advisory. Nothing here changes a price, a status or a
payment, and a report that failed says so rather than blocking anything.
"""

import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.pdf_rules import QualityThresholds, assess_document
from app.errors import NotFound
from app.gateways.storage import Storage
from app.models import QualityReport, Upload
from app.quality.analyzer import AnalysisTimeout, analyze_pdf

#: Which version of the algorithm produced the numbers. It goes into
#: every report, so two reports made by different code are never
#: compared without knowing they were made the same way.
ALGORITHM_VERSION = "1"

#: How long one file may take to be analysed. A file that is slow is a
#: failed report, not a report that hangs the worker.
ANALYSIS_TIMEOUT_SECONDS = 60.0


def get_owned_upload(session: Session, upload_id: uuid.UUID, customer_id: uuid.UUID) -> Upload:
    """The customer's own upload, or nothing at all.

    Another customer's upload is not found, rather than refused, so the
    answer does not tell a stranger that the file exists.
    """
    upload = session.scalar(
        select(Upload).where(Upload.id == upload_id, Upload.customer_id == customer_id)
    )
    if upload is None:
        raise NotFound("Upload not found")
    return upload


def trigger(session: Session, *, upload: Upload) -> QualityReport:
    """Ask for the file to be analysed.

    Asking twice gives the same report: the analysis is done once, and
    the report is the record of that one analysis.
    """
    report = session.scalar(select(QualityReport).where(QualityReport.upload_id == upload.id))
    if report is None:
        report = QualityReport(
            upload_id=upload.id,
            status="PENDING",
            pages=[],
            summary={},
            algorithm_version=ALGORITHM_VERSION,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
    return report


def get_report(session: Session, *, upload: Upload, customer_id: uuid.UUID) -> QualityReport:
    get_owned_upload(session, upload.id, customer_id)
    report = session.scalar(select(QualityReport).where(QualityReport.upload_id == upload.id))
    if report is None:
        raise NotFound("Quality report not found")
    return report


def acknowledge(session: Session, *, upload: Upload, customer_id: uuid.UUID) -> QualityReport:
    """Record that the customer has seen the warnings and gone ahead.

    The acknowledgement is a fact about the customer, not a permission:
    the order can be placed without it.
    """
    report = get_report(session, upload=upload, customer_id=customer_id)
    report.acknowledged = True
    session.commit()
    session.refresh(report)
    return report


def run_one(session: Session, *, report_id: uuid.UUID, storage: Storage, now: datetime) -> bool:
    """Analyse one report that is waiting.

    Returns whether this call did the work. A report that another worker
    has taken is left alone, and a report that has already been done is
    not done twice.
    """
    report = session.scalar(
        select(QualityReport).where(QualityReport.id == report_id).with_for_update(skip_locked=True)
    )
    if report is None or report.status not in {"PENDING", "RUNNING"}:
        return False
    upload = session.get(Upload, report.upload_id)
    if upload is None or upload.file_deleted_at is not None:
        report.status = "FAILED"
        report.error = "The file is no longer stored"
        report.completed_at = now
        session.commit()
        return True

    report.status = "RUNNING"
    report.started_at = now
    report.algorithm_version = ALGORITHM_VERSION
    session.commit()
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temp:
            storage.download_to_path(upload.file_key, Path(temp.name))
            measured = analyze_pdf(
                Path(temp.name),
                timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
                # The bound is the upload limit, so that a file which
                # was accepted can be analysed. An operator who raises
                # the page limit does not get files whose report fails
                # for having too many pages.
                max_pages=get_settings().max_pages,
            )
        pages = assess_document(measured.pages, QualityThresholds())
        report.pages = [
            {
                "page_number": page.page_number,
                "min_effective_dpi": page.min_effective_dpi,
                "blur_score": page.blur_score,
                "flags": list(page.flags),
            }
            for page in pages
        ]
        report.summary = {
            "page_count": len(pages),
            "flagged_pages": sum(1 for page in pages if page.flagged),
            "flagged": any(page.flagged for page in pages),
        }
        report.status = "DONE"
    except AnalysisTimeout:
        report.status = "FAILED"
        report.error = "The quality check took too long and was stopped"
    except Exception as exc:
        # A failed analysis is a failed report. The customer is told the
        # check did not happen, and the order is not affected.
        report.status = "FAILED"
        report.error = "The file could not be analysed"
        report.summary = {"reason": type(exc).__name__}
    report.completed_at = now
    session.commit()
    return True
