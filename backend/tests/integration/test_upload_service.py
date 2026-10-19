import hashlib
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.config import Settings
from app.errors import FileTooLarge, PdfTooManyPages
from app.gateways.storage import MemoryStorage
from app.services import upload_service
from sqlalchemy.orm import Session
from tests.factories import create_user
from tests.fixtures.pdf_files import make_pdf


def test_oversized_stream_is_rejected_before_storage(db_session: Session, tmp_path: Path) -> None:
    customer = create_user(db_session, email="customer@example.com")
    storage = MemoryStorage()
    settings = Settings(max_upload_mb=1)

    with pytest.raises(FileTooLarge):
        upload_service.create_upload(
            db_session,
            storage,
            settings,
            customer_id=customer.id,
            original_filename="big.pdf",
            source=io.BytesIO(b"%PDF-1.7" + b"0" * (2 * 1024 * 1024)),
        )

    assert storage.objects == {}


def test_too_many_pages_is_rejected(db_session: Session, tmp_path: Path) -> None:
    customer = create_user(db_session, email="customer@example.com")
    pdf_path = make_pdf(tmp_path / "many.pdf", pages=3)
    settings = Settings(max_pages=2)

    with pytest.raises(PdfTooManyPages), pdf_path.open("rb") as source:
        upload_service.create_upload(
            db_session,
            MemoryStorage(),
            settings,
            customer_id=customer.id,
            original_filename="many.pdf",
            source=source,
        )


def test_successful_upload_records_digest_and_retention(
    db_session: Session, tmp_path: Path
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    pdf_path = make_pdf(tmp_path / "ok.pdf", pages=2)
    storage = MemoryStorage()

    upload = upload_service.create_upload(
        db_session,
        storage,
        Settings(),
        customer_id=customer.id,
        original_filename="ok.pdf",
        source=pdf_path.open("rb"),
    )

    assert upload.page_count == 2
    assert upload.sha256 == hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert upload.size_bytes == pdf_path.stat().st_size
    assert storage.objects[upload.file_key] == pdf_path.read_bytes()
    assert upload.delete_after is not None
    expected = datetime.now(UTC) + timedelta(hours=Settings().file_retention_hours)
    assert abs((upload.delete_after - expected).total_seconds()) < 60


def test_long_filenames_are_truncated(db_session: Session, tmp_path: Path) -> None:
    customer = create_user(db_session, email="customer@example.com")
    pdf_path = make_pdf(tmp_path / "long.pdf")

    upload = upload_service.create_upload(
        db_session,
        MemoryStorage(),
        Settings(),
        customer_id=customer.id,
        original_filename="x" * 500 + ".pdf",
        source=pdf_path.open("rb"),
    )

    assert len(upload.original_filename) == 255


def test_hundred_page_pdf_is_accepted(db_session: Session, tmp_path: Path) -> None:
    customer = create_user(db_session, email="customer@example.com")
    pdf_path = make_pdf(tmp_path / "book.pdf", pages=100)

    upload = upload_service.create_upload(
        db_session,
        MemoryStorage(),
        Settings(),
        customer_id=customer.id,
        original_filename="book.pdf",
        source=pdf_path.open("rb"),
    )

    assert upload.page_count == 100
