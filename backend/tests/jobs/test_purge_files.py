"""Tests for the purge_files job.

The file has to go, and the row has to stay.
"""

from datetime import UTC, datetime, timedelta

from app.gateways.storage import MemoryStorage
from app.jobs import purge_files
from app.models import Upload
from sqlalchemy.orm import Session
from tests.factories import create_upload_row, create_user

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class BrokenStorage(MemoryStorage):
    """Storage whose delete always fails, to test the retry path."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def delete(self, key: str) -> None:
        self.attempts += 1
        raise RuntimeError("storage is down")


def _upload(session: Session, *, delete_after: datetime) -> Upload:
    customer = create_user(session, email="customer@example.com")
    upload = create_upload_row(session, customer=customer, page_count=1)
    upload.delete_after = delete_after
    session.commit()
    return upload


def test_a_file_past_its_retention_is_deleted(db_session: Session) -> None:
    upload = _upload(db_session, delete_after=NOW - timedelta(minutes=1))
    storage = MemoryStorage()
    storage.objects[upload.file_key] = b"%PDF-1.7"

    deleted = purge_files.run(db_session, storage=storage, now=NOW)

    assert deleted == 1
    db_session.refresh(upload)
    assert upload.file_deleted_at == NOW
    assert upload.file_key not in storage.objects


def test_a_file_inside_its_retention_is_kept(db_session: Session) -> None:
    upload = _upload(db_session, delete_after=NOW + timedelta(hours=1))
    storage = MemoryStorage()
    storage.objects[upload.file_key] = b"%PDF-1.7"

    deleted = purge_files.run(db_session, storage=storage, now=NOW)

    assert deleted == 0
    db_session.refresh(upload)
    assert upload.file_deleted_at is None
    assert upload.file_key in storage.objects


def test_running_the_job_twice_deletes_nothing_the_second_time(
    db_session: Session,
) -> None:
    _upload(db_session, delete_after=NOW - timedelta(minutes=1))
    storage = MemoryStorage()

    first = purge_files.run(db_session, storage=storage, now=NOW)
    second = purge_files.run(db_session, storage=storage, now=NOW)

    assert first == 1
    assert second == 0


def test_a_file_that_failed_to_delete_is_tried_again(db_session: Session) -> None:
    upload = _upload(db_session, delete_after=NOW - timedelta(minutes=1))
    storage = BrokenStorage()

    deleted = purge_files.run(db_session, storage=storage, now=NOW)

    assert deleted == 0
    db_session.refresh(upload)
    assert upload.file_deleted_at is None
    assert storage.attempts == 1


def test_the_row_is_kept_after_the_file_is_deleted(db_session: Session) -> None:
    upload = _upload(db_session, delete_after=NOW - timedelta(minutes=1))
    storage = MemoryStorage()

    purge_files.run(db_session, storage=storage, now=NOW)

    assert db_session.get(Upload, upload.id) is not None
