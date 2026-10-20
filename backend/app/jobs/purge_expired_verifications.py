"""Delete the verification tokens that are past their time.

A token is a secret until it is used, and the ones that are never used
are the ones that were sent to an address nobody reads. They stop
working on their own, but the rows stay, and the table would grow for
as long as the application runs.

The rows are small and they carry nothing but a hash, so there is
nothing to keep. They are deleted in batches, and the batch is claimed
with a lock, so two workers do not delete the same rows twice.
"""

import logging
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import EmailVerificationToken

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def run(session: Session, *, now: datetime) -> int:
    """Delete the tokens that have expired.

    Returns how many were deleted. Safe to run twice: a token that is
    gone is not deleted again.
    """
    token_ids = list(
        session.scalars(
            select(EmailVerificationToken.id)
            .where(EmailVerificationToken.expires_at <= now)
            .order_by(EmailVerificationToken.expires_at.asc())
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )
    if not token_ids:
        return 0
    session.execute(delete(EmailVerificationToken).where(EmailVerificationToken.id.in_(token_ids)))
    session.commit()
    logger.info("purge_expired_verifications", extra={"deleted": len(token_ids)})
    return len(token_ids)
