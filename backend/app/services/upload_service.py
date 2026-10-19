import hashlib
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import (
    FileNotPDF,
    FileTooLarge,
    NotFound,
    PdfCorrupt,
    PdfEncrypted,
    PdfTooManyPages,
)
from app.gateways.storage import Storage
from app.models import Upload
from app.schemas.order import FileUrlResponse

CHUNK_SIZE = 1024 * 1024
PDF_MAGIC = b"%PDF-"
MAX_FILENAME_LENGTH = 255
DOWNLOAD_URL_TTL_SECONDS = 300


def create_upload(
    session: Session,
    storage: Storage,
    settings: Settings,
    *,
    customer_id: uuid.UUID,
    original_filename: str,
    source: IO[bytes],
) -> Upload:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(suffix=".pdf") as temp_file:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise FileTooLarge(f"File exceeds the {settings.max_upload_mb} MB limit")
            digest.update(chunk)
            temp_file.write(chunk)
        temp_file.flush()
        if size < len(PDF_MAGIC):
            raise FileNotPDF("File does not look like a PDF")
        temp_file.seek(0)
        if temp_file.read(len(PDF_MAGIC)) != PDF_MAGIC:
            raise FileNotPDF("File does not look like a PDF")
        page_count = _inspect_pdf(temp_file.name, settings.max_pages)
        file_key = f"uploads/{uuid.uuid4().hex}.pdf"
        storage.put_file(file_key, Path(temp_file.name))

    upload = Upload(
        customer_id=customer_id,
        file_key=file_key,
        original_filename=original_filename[:MAX_FILENAME_LENGTH],
        size_bytes=size,
        sha256=digest.hexdigest(),
        page_count=page_count,
        delete_after=datetime.now(UTC) + timedelta(hours=settings.file_retention_hours),
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    return upload


def get_upload(session: Session, *, upload_id: uuid.UUID, customer_id: uuid.UUID) -> Upload:
    upload = session.scalar(
        select(Upload).where(Upload.id == upload_id, Upload.customer_id == customer_id)
    )
    if upload is None:
        raise NotFound("Upload not found")
    return upload


def presigned_download(
    storage: Storage, upload: Upload, *, expires_seconds: int = DOWNLOAD_URL_TTL_SECONDS
) -> FileUrlResponse:
    """A short-lived link to the stored PDF.

    The bucket is private, so this is the only way to read a file. The link
    is valid for five minutes and the object is fetched as an attachment so
    it never renders inside the app.
    """
    if upload.file_deleted_at is not None:
        raise NotFound("This file is no longer available")
    url = storage.presigned_get_url(
        upload.file_key,
        expires_seconds=expires_seconds,
        download_filename=upload.original_filename,
    )
    return FileUrlResponse(
        url=url,
        expires_in_seconds=expires_seconds,
        filename=upload.original_filename,
    )


def _inspect_pdf(path: str, max_pages: int) -> int:
    try:
        document = pymupdf.open(path)
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise PdfCorrupt("PDF could not be read") from exc
    try:
        if document.needs_pass:
            raise PdfEncrypted("PDF is password protected")
        page_count = int(document.page_count)
    finally:
        document.close()
    if page_count == 0:
        raise PdfCorrupt("PDF has no pages")
    if page_count > max_pages:
        raise PdfTooManyPages(f"PDF has more than {max_pages} pages")
    return page_count
