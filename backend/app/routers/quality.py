import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_customer
from app.models import QualityReport, User
from app.rate_limit import user_rate_limit
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.quality import QualityReportResponse
from app.services import quality_service

router = APIRouter(tags=["quality"], responses=ERROR_RESPONSES)


def _response(report: QualityReport) -> QualityReportResponse:
    return QualityReportResponse.model_validate(report, from_attributes=True)


@router.post(
    "/uploads/{upload_id}/quality",
    response_model=QualityReportResponse,
    dependencies=[Depends(user_rate_limit(60, 60, "quality_trigger"))],
)
def trigger_quality(
    upload_id: uuid.UUID,
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> QualityReportResponse:
    """Ask for the file to be checked.

    The check itself happens in the worker, so this answers at once. The
    report is one per file, so asking twice does not start a second
    analysis, which is why the limit here is not tight: the front end
    asks for the check when the customer reaches the review step, and
    the answer is cheap.
    """
    upload = quality_service.get_owned_upload(session, upload_id, user.id)
    return _response(quality_service.trigger(session, upload=upload))


@router.post(
    "/uploads/{upload_id}/quality/acknowledge",
    response_model=QualityReportResponse,
    dependencies=[Depends(user_rate_limit(30, 60, "quality_acknowledge"))],
)
def acknowledge_quality(
    upload_id: uuid.UUID,
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> QualityReportResponse:
    """Record that the customer has seen the warnings.

    The acknowledgement is a fact about the customer. It is not a
    permission, and the order can be placed without it.
    """
    upload = quality_service.get_owned_upload(session, upload_id, user.id)
    return _response(quality_service.acknowledge(session, upload=upload, customer_id=user.id))


@router.get(
    "/uploads/{upload_id}/quality",
    response_model=QualityReportResponse,
    dependencies=[Depends(user_rate_limit(600, 60, "quality_read"))],
)
def get_quality(
    upload_id: uuid.UUID,
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> QualityReportResponse:
    """The quality report for one of the customer's own files.

    Another customer's file is not found, rather than refused, so the
    answer does not tell a stranger that it exists.

    The read limit is generous because the front end polls while the
    worker measures the file, and the worker runs every thirty seconds.
    A customer with a few files open is a few reads every two seconds,
    which is well inside the limit.
    """
    upload = quality_service.get_owned_upload(session, upload_id, user.id)
    return _response(quality_service.get_report(session, upload=upload, customer_id=user.id))
