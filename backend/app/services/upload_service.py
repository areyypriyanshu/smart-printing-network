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
from app.domain.documents import describe, detect
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
from app.services.document_service import ConversionError, convert_to_pdf

CHUNK_SIZE = 1024 * 1024
PDF_MAGIC = b"%PDF-"
#: How many bytes are read to work out what a file is.
HEAD_BYTES = 8192
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
    with tempfile.NamedTemporaryFile(suffix=".bin") as temp_file:
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
        temp_file.seek(0)
        head = temp_file.read(HEAD_BYTES)
        temp_file.seek(0)

        kind = detect(head, filename=original_filename)
        info = describe(kind)
        if not info.printable:
            # The message names the file and the fix, because "this is not
            # a PDF" is a dead end for a student who simply has the wrong
            # file.
            raise FileNotPDF(info.message or "We cannot print this kind of file")

        if info.converted:
            page_count, printable = _convert(temp_file.name, kind)
        else:
            page_count = _inspect_pdf(temp_file.name, settings.max_pages)
            printable = Path(temp_file.name)

        file_key = f"uploads/{uuid.uuid4().hex}.pdf"
        storage.put_file(file_key, printable)

    upload = Upload(
        customer_id=customer_id,
        file_key=file_key,
        original_filename=original_filename[:MAX_FILENAME_LENGTH],
        size_bytes=size,
        sha256=digest.hexdigest(),
        page_count=page_count,
        source_format=info.kind,
        delete_after=datetime.now(UTC) + timedelta(hours=settings.file_retention_hours),
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    return upload


def _convert(source_path: str, kind: str) -> tuple[int, Path]:
    """Turn an Office document into the PDF that will be printed."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as target:
        target_path = Path(target.name)
    try:
        page_count = convert_to_pdf(Path(source_path), target_path, kind=kind)
    except ConversionError as exc:
        target_path.unlink(missing_ok=True)
        raise FileNotPDF(
            f"We could not read that {kind.upper()} file. Open it in Word, "
            "Excel or Google Docs and download it as a PDF, then upload that."
        ) from exc
    return page_count, target_path


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
    download_name = printable_filename(upload)
    url = storage.presigned_get_url(
        upload.file_key,
        expires_seconds=expires_seconds,
        download_filename=download_name,
    )
    return FileUrlResponse(
        url=url,
        expires_in_seconds=expires_seconds,
        filename=download_name,
    )


def printable_filename(upload: Upload) -> str:
    """The name the file is downloaded under.

    A converted document is a PDF, even though the customer uploaded a
    .docx. Handing the shop a PDF called "notes.docx" would be a file
    their machine cannot open, so the extension follows what we print.
    """
    if upload.source_format is None or upload.source_format == "pdf":
        return upload.original_filename
    stem = upload.original_filename.rpartition(".")[0] or upload.original_filename
    return f"{stem}.pdf"


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
