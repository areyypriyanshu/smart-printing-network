import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.gateways.storage import MemoryStorage
from app.models import Upload
from app.services.upload_service import printable_filename
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import create_user, login_headers
from tests.fixtures.pdf_files import make_corrupt_pdf, make_encrypted_pdf, make_pdf
from tests.office_fixtures import docx_bytes, png_bytes, xlsx_bytes

UPLOADS = "/api/v1/uploads"


def _upload(client: TestClient, headers: dict[str, str], path: Path, filename: str | None = None):
    with path.open("rb") as handle:
        return client.post(
            UPLOADS,
            headers=headers,
            files={"file": (filename or path.name, handle, "application/pdf")},
        )


def test_upload_valid_pdf_returns_metadata_and_stores_file(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    pdf_path = make_pdf(tmp_path / "valid.pdf", pages=3)
    expected_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    response = _upload(client, headers, pdf_path)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["page_count"] == 3
    assert body["original_filename"] == "valid.pdf"
    assert body["size_bytes"] == pdf_path.stat().st_size

    storage: MemoryStorage = client.app.state.storage
    assert len(storage.objects) == 1
    key = next(iter(storage.objects))
    assert key.startswith("uploads/")
    assert "valid" not in key
    assert storage.objects[key] == pdf_path.read_bytes()

    upload = db_session.query(Upload).one()
    assert upload.sha256 == expected_sha
    assert upload.delete_after is not None
    expected_delete_after = datetime.now(UTC) + timedelta(hours=24)
    assert abs((upload.delete_after - expected_delete_after).total_seconds()) < 60


def test_upload_rejects_a_text_file_renamed_as_pdf(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    fake_pdf = tmp_path / "notes.pdf"
    fake_pdf.write_text("just some text, not a pdf")

    response = _upload(client, headers, fake_pdf)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_NOT_PDF"
    assert client.app.state.storage.objects == {}


def test_upload_rejects_zero_byte_file(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")

    response = _upload(client, headers, empty)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_NOT_PDF"


def test_upload_rejects_corrupt_pdf(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    corrupt = make_corrupt_pdf(tmp_path / "corrupt.pdf")

    response = _upload(client, headers, corrupt)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PDF_CORRUPT"
    assert client.app.state.storage.objects == {}


def test_upload_rejects_encrypted_pdf(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    encrypted = make_encrypted_pdf(tmp_path / "locked.pdf")

    response = _upload(client, headers, encrypted)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PDF_ENCRYPTED"
    assert client.app.state.storage.objects == {}


def test_upload_requires_authentication(client: TestClient, tmp_path: Path) -> None:
    pdf_path = make_pdf(tmp_path / "valid.pdf")

    response = _upload(client, {}, pdf_path)

    assert response.status_code == 401


def test_upload_forbidden_for_vendors(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="vendor@example.com", role="vendor")
    headers = login_headers(client, "vendor@example.com")
    pdf_path = make_pdf(tmp_path / "valid.pdf")

    response = _upload(client, headers, pdf_path)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_get_upload_returns_own_upload(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    created = _upload(client, headers, make_pdf(tmp_path / "valid.pdf")).json()

    response = client.get(f"{UPLOADS}/{created['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_upload_of_another_customer_returns_404(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="owner@example.com")
    create_user(db_session, email="snooper@example.com")
    owner_headers = login_headers(client, "owner@example.com")
    snooper_headers = login_headers(client, "snooper@example.com")
    created = _upload(client, owner_headers, make_pdf(tmp_path / "valid.pdf")).json()

    response = client.get(f"{UPLOADS}/{created['id']}", headers=snooper_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_upload_rejects_an_image_with_a_message_that_says_what_to_do(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """A student with a screenshot should be told how to fix it."""
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    image = tmp_path / "screenshot.png"
    image.write_bytes(png_bytes())

    response = _upload(client, headers, image)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "FILE_NOT_PDF"
    assert "Download as PDF" in body["error"]["message"]
    assert client.app.state.storage.objects == {}


def test_upload_rejects_an_old_word_file_with_a_message_that_says_what_to_do(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    old_word = tmp_path / "old.doc"
    old_word.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)

    response = _upload(client, headers, old_word)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "FILE_NOT_PDF"
    assert "Save As" in body["error"]["message"]


def test_upload_accepts_a_word_document_and_converts_it(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """A .docx is printed as a PDF, and the shop downloads a PDF."""
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    document = tmp_path / "report.docx"
    document.write_bytes(docx_bytes([("", "My project report.")], with_image=True))

    response = _upload(client, headers, document)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["page_count"] == 1
    assert body["original_filename"] == "report.docx"

    storage: MemoryStorage = client.app.state.storage
    assert len(storage.objects) == 1
    key = next(iter(storage.objects))
    assert key.startswith("uploads/")
    assert storage.objects[key].startswith(b"%PDF-")

    upload = db_session.query(Upload).one()
    assert upload.source_format == "docx"


def test_upload_accepts_a_spreadsheet_and_converts_it(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    sheet = tmp_path / "marks.xlsx"
    sheet.write_bytes(xlsx_bytes([["Name", "Mark"], ["Asha", "90"]]))

    response = _upload(client, headers, sheet)

    assert response.status_code == 201, response.text
    assert response.json()["page_count"] == 1
    upload = db_session.query(Upload).one()
    assert upload.source_format == "xlsx"


def test_a_converted_document_is_downloaded_as_a_pdf(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """The shop must not be handed a PDF called report.docx."""
    create_user(db_session, email="customer@example.com")
    headers = login_headers(client, "customer@example.com")
    document = tmp_path / "report.docx"
    document.write_bytes(docx_bytes())

    response = _upload(client, headers, document)

    assert response.status_code == 201, response.text
    upload = db_session.query(Upload).one()
    assert printable_filename(upload) == "report.pdf"
