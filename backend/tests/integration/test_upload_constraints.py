"""The rules the database holds about an upload.

A check constraint is the last line of defence. These tests write rows
that break the rules and show that the database refuses them.
"""

import uuid

import pytest
from app.models import Upload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.factories import create_user


def _upload(session: Session, source_format: str | None) -> Upload:
    customer = create_user(session, email=f"user-{uuid.uuid4().hex}@example.com")
    upload = Upload(
        customer_id=customer.id,
        file_key=f"uploads/{uuid.uuid4().hex}.pdf",
        original_filename="file.pdf",
        size_bytes=10,
        sha256="0" * 64,
        page_count=1,
        source_format=source_format,
    )
    session.add(upload)
    return upload


def test_an_upload_may_have_no_source_format(db_session: Session) -> None:
    _upload(db_session, None)
    db_session.commit()

    assert db_session.query(Upload).one().source_format is None


def test_an_upload_may_say_it_arrived_as_a_word_document(db_session: Session) -> None:
    _upload(db_session, "docx")
    db_session.commit()

    assert db_session.query(Upload).one().source_format == "docx"


def test_an_upload_with_a_made_up_source_format_is_refused(db_session: Session) -> None:
    _upload(db_session, "executable")

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
