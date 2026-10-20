"""The limits an upload is held to, and what a deleted file cannot do.

An upload is the largest thing a stranger can put on the platform, and
the limits that hold it are the difference between "somebody sent a big
file" and "somebody filled the disk".

These are the tests for the two limits that were missing: the page limit
for a converted document, and the rule that a file the platform has
already deleted cannot be quoted for or ordered.
"""

import uuid
from pathlib import Path

import pytest
from app.config import Settings
from app.errors import FileUnavailable, PdfTooManyPages
from app.gateways.storage import MemoryStorage
from app.models import Upload
from app.schemas.quote import QuoteRequest
from app.services import quote_service, upload_service
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import create_upload_row, create_user
from tests.office_fixtures import docx_bytes

ORDERS = "/api/v1/orders"
QUOTES = "/api/v1/quotes"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "payment_provider": "fake",
        "fake_webhook_secret": "a-key-the-operator-chose",
        "env": "local",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_a_converted_document_over_the_page_limit_is_refused(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A converted document is printed as a PDF, so the page limit applies.

    The limit was only applied to a PDF that was uploaded directly, so a
    Word document with a thousand pages was converted, stored and priced
    as a job the platform would refuse to print.
    """
    customer = create_user(db_session, email="customer@example.com")
    source = tmp_path / "long.docx"
    source.write_bytes(docx_bytes([("", "a paragraph")]))
    converted = tmp_path / "long.pdf"
    converted.write_bytes(b"%PDF-1.7\n")

    monkeypatch.setattr(
        "app.services.upload_service._convert",
        lambda source_path, kind: (5000, converted),
    )

    with pytest.raises(PdfTooManyPages):
        upload_service.create_upload(
            db_session,
            MemoryStorage(),
            _settings(max_pages=300),
            customer_id=customer.id,
            original_filename="long.docx",
            source=source.open("rb"),
        )


def test_a_converted_document_inside_the_page_limit_is_kept(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    source = tmp_path / "short.docx"
    source.write_bytes(docx_bytes([("", "a paragraph")]))
    converted = tmp_path / "short.pdf"
    converted.write_bytes(b"%PDF-1.7\n")

    monkeypatch.setattr(
        "app.services.upload_service._convert",
        lambda source_path, kind: (3, converted),
    )
    storage = MemoryStorage()

    upload = upload_service.create_upload(
        db_session,
        storage,
        _settings(max_pages=300),
        customer_id=customer.id,
        original_filename="short.docx",
        source=source.open("rb"),
    )

    assert upload.page_count == 3
    assert len(storage.objects) == 1


def test_the_converted_file_does_not_stay_on_the_disk(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The converted PDF is scratch space, not the stored object.

    It is removed as soon as the object has been written, so a conversion
    never leaves a file behind on the container.
    """
    customer = create_user(db_session, email="customer@example.com")
    source = tmp_path / "short.docx"
    source.write_bytes(docx_bytes([("", "a paragraph")]))
    converted = tmp_path / "short.pdf"
    converted.write_bytes(b"%PDF-1.7\n")

    monkeypatch.setattr(
        "app.services.upload_service._convert",
        lambda source_path, kind: (3, converted),
    )

    upload_service.create_upload(
        db_session,
        MemoryStorage(),
        _settings(max_pages=300),
        customer_id=customer.id,
        original_filename="short.docx",
        source=source.open("rb"),
    )

    assert not converted.exists()


def test_a_file_the_platform_deleted_cannot_be_quoted(db_session: Session) -> None:
    """A tombstoned file has no object behind it any more.

    The quote is refused before a price is shown, so the customer is not
    asked to pay for a job that cannot be done.
    """
    customer = create_user(db_session, email="customer@example.com")
    upload = create_upload_row(db_session, customer=customer, page_count=3)
    upload.file_deleted_at = upload.created_at
    db_session.commit()

    with pytest.raises(FileUnavailable):
        quote_service.quote(
            db_session,
            customer_id=customer.id,
            request=QuoteRequest(
                upload_id=upload.id,
                shop_id=uuid.uuid4(),
                paper_size="A4",
                color=False,
                duplex=False,
                copies=1,
            ),
        )


def test_a_file_the_platform_deleted_cannot_be_ordered(
    client: TestClient, db_session: Session
) -> None:
    """The order is refused for the same reason the quote is.

    The order is where the money is taken, so it must not be reachable
    either.
    """
    from tests.factories import create_full_rate_table, create_shop, login_headers

    customer = create_user(db_session, email="customer@example.com")
    vendor = create_user(db_session, email="vendor@example.com", role="vendor")
    shop = create_shop(db_session, owner=vendor)
    create_full_rate_table(db_session, shop, base_paise=200)
    upload = create_upload_row(db_session, customer=customer, page_count=3)
    upload.file_deleted_at = upload.created_at
    db_session.commit()
    headers = login_headers(client, "customer@example.com")

    response = client.post(
        ORDERS,
        headers={**headers, "Idempotency-Key": "key-1"},
        json={
            "upload_id": str(upload.id),
            "shop_id": str(shop.id),
            "paper_size": "A4",
            "color": False,
            "duplex": False,
            "copies": 1,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FILE_UNAVAILABLE"
    assert db_session.query(Upload).count() == 1
