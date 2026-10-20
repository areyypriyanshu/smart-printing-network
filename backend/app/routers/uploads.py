import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_customer, get_storage, require_verified_email
from app.gateways.storage import Storage
from app.models import Upload, User
from app.rate_limit import user_rate_limit
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.upload import UploadResponse
from app.services import upload_service

router = APIRouter(tags=["uploads"], responses=ERROR_RESPONSES)


@router.post(
    "/uploads",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadResponse,
    dependencies=[Depends(user_rate_limit(10, 60, "uploads"))],
)
def create_upload(
    file: UploadFile = File(...),
    user: User = Depends(require_verified_email),
    session: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> Upload:
    return upload_service.create_upload(
        session,
        storage,
        get_settings(),
        customer_id=user.id,
        original_filename=file.filename or "document.pdf",
        source=file.file,
    )


@router.get("/uploads/{upload_id}", response_model=UploadResponse)
def get_upload(
    upload_id: uuid.UUID,
    user: User = Depends(get_customer),
    session: Session = Depends(get_db),
) -> Upload:
    return upload_service.get_upload(session, upload_id=upload_id, customer_id=user.id)
