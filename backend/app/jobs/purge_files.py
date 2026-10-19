"""Delete the stored PDFs that are past their retention.

A customer's file is kept while the order is alive and for a short
window afterwards, so a shop can still open a finished order and the
customer can still check what they sent. After that the object is deleted
and the row is kept for the audit trail.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gateways.storage import Storage
from app.models import Upload

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def run(session: Session, *, storage: Storage, now: datetime) -> int:
    """Delete the files whose retention window has closed.

    Returns how many files were deleted. Safe to run twice: a deleted
    file has `file_deleted_at` set, so the second run skips it.
    """
    upload_ids = list(
        session.scalars(
            select(Upload.id)
            .where(
                Upload.file_deleted_at.is_(None),
                Upload.delete_after.is_not(None),
                Upload.delete_after <= now,
            )
            .order_by(Upload.delete_after.asc())
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )

    deleted = 0
    for upload_id in upload_ids:
        upload = session.get(Upload, upload_id)
        if upload is None or upload.file_deleted_at is not None:
            continue
        try:
            storage.delete(upload.file_key)
        except Exception as exc:
            # Leave file_deleted_at unset so the next run tries again. The
            # object stays private in the meantime.
            logger.error(
                "purge_files_delete_failed",
                extra={"upload_id": str(upload.id), "reason": str(exc)},
            )
            session.rollback()
            continue
        upload.file_deleted_at = now
        session.commit()
        deleted += 1
    return deleted
