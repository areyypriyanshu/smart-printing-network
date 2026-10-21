from datetime import UTC, datetime
from pathlib import Path

from app.gateways.storage import MemoryStorage
from app.jobs import analyze_quality
from app.models import QualityReport
from app.services.quality_service import run_one
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import create_upload_row, create_user, login_headers
from tests.fixtures.pdf_files import make_pdf

QUALITY = "/api/v1/uploads/{}/quality"


class BrokenStorage:
    """A storage that cannot hand the file over."""

    def download_to_path(self, key: str, path: Path) -> None:
        raise OSError("the object store is not answering")


def test_customer_can_queue_and_read_quality_report(
    client: TestClient, db_session: Session
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    upload = create_upload_row(session=db_session, customer=customer)
    headers = login_headers(client, customer.email)

    created = client.post(QUALITY.format(upload.id), headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "PENDING"
    duplicate = client.post(QUALITY.format(upload.id), headers=headers)
    assert duplicate.json()["id"] == created.json()["id"]

    fetched = client.get(QUALITY.format(upload.id), headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["upload_id"] == str(upload.id)


def test_quality_report_is_object_authorized_and_acknowledgable(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="owner@example.com")
    other = create_user(db_session, email="other@example.com")
    upload = create_upload_row(session=db_session, customer=owner)
    owner_headers = login_headers(client, owner.email)
    other_headers = login_headers(client, other.email)
    client.post(QUALITY.format(upload.id), headers=owner_headers)

    forbidden = client.get(QUALITY.format(upload.id), headers=other_headers)
    assert forbidden.status_code == 404
    acknowledged = client.post(QUALITY.format(upload.id) + "/acknowledge", headers=owner_headers)
    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged"] is True


def test_a_vendor_cannot_see_a_customers_quality_report(
    client: TestClient, db_session: Session
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    create_user(db_session, email="vendor@example.com", role="vendor")
    upload = create_upload_row(session=db_session, customer=customer)
    vendor_headers = login_headers(client, "vendor@example.com")

    response = client.get(QUALITY.format(upload.id), headers=vendor_headers)

    assert response.status_code == 403


def test_the_quality_endpoints_need_authentication(client: TestClient, db_session: Session) -> None:
    customer = create_user(db_session, email="customer@example.com")
    upload = create_upload_row(session=db_session, customer=customer)

    assert client.get(QUALITY.format(upload.id)).status_code == 401
    assert client.post(QUALITY.format(upload.id)).status_code == 401


def test_a_report_for_a_file_that_was_never_asked_for_is_not_found(
    client: TestClient, db_session: Session
) -> None:
    customer = create_user(db_session, email="customer@example.com")
    upload = create_upload_row(session=db_session, customer=customer)
    headers = login_headers(client, customer.email)

    response = client.get(QUALITY.format(upload.id), headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_quality_worker_completes_report_from_private_memory_storage(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    customer = create_user(db_session, email="worker@example.com")
    upload = create_upload_row(session=db_session, customer=customer)
    pdf = make_pdf(tmp_path / "quality.pdf", pages=1)
    storage: MemoryStorage = client.app.state.storage
    storage.put_file(upload.file_key, pdf)
    report = QualityReport(upload_id=upload.id, status="PENDING", pages=[], summary={})
    db_session.add(report)
    db_session.commit()

    assert run_one(
        db_session,
        report_id=report.id,
        storage=storage,
        now=datetime.now(UTC),
    )
    db_session.refresh(report)
    assert report.status == "DONE"
    assert len(report.pages) == 1
    assert report.algorithm_version


def test_the_job_does_not_analyse_the_same_report_twice(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    customer = create_user(db_session, email="twice@example.com")
    upload = create_upload_row(session=db_session, customer=customer)
    pdf = make_pdf(tmp_path / "quality.pdf", pages=1)
    storage: MemoryStorage = client.app.state.storage
    storage.put_file(upload.file_key, pdf)
    report = QualityReport(upload_id=upload.id, status="PENDING", pages=[], summary={})
    db_session.add(report)
    db_session.commit()
    now = datetime.now(UTC)

    assert analyze_quality.run(db_session, storage=storage, now=now) == 1
    assert analyze_quality.run(db_session, storage=storage, now=now) == 0


def test_a_report_for_a_deleted_file_fails_without_blocking_anything(
    client: TestClient, db_session: Session
) -> None:
    customer = create_user(db_session, email="deleted@example.com")
    upload = create_upload_row(session=db_session, customer=customer)
    upload.file_deleted_at = datetime.now(UTC)
    report = QualityReport(upload_id=upload.id, status="PENDING", pages=[], summary={})
    db_session.add(report)
    db_session.commit()

    assert run_one(
        db_session,
        report_id=report.id,
        storage=client.app.state.storage,
        now=datetime.now(UTC),
    )
    db_session.refresh(report)
    assert report.status == "FAILED"
    assert report.error is not None


def test_a_report_fails_when_the_file_cannot_be_read(
    client: TestClient, db_session: Session
) -> None:
    customer = create_user(db_session, email="unreadable@example.com")
    upload = create_upload_row(session=db_session, customer=customer)
    report = QualityReport(upload_id=upload.id, status="PENDING", pages=[], summary={})
    db_session.add(report)
    db_session.commit()

    assert run_one(
        db_session,
        report_id=report.id,
        storage=BrokenStorage(),
        now=datetime.now(UTC),
    )
    db_session.refresh(report)
    assert report.status == "FAILED"
    # The reason is a sentence for the customer, not the internals.
    assert report.error == "The file could not be analysed"
    assert report.summary == {"reason": "OSError"}


def test_a_file_that_is_not_a_pdf_fails_the_report_without_raising(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    customer = create_user(db_session, email="notapdf@example.com")
    upload = create_upload_row(session=db_session, customer=customer)
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf at all")
    storage: MemoryStorage = client.app.state.storage
    storage.put_file(upload.file_key, broken)
    report = QualityReport(upload_id=upload.id, status="PENDING", pages=[], summary={})
    db_session.add(report)
    db_session.commit()

    assert run_one(
        db_session,
        report_id=report.id,
        storage=storage,
        now=datetime.now(UTC),
    )
    db_session.refresh(report)
    assert report.status == "FAILED"


def test_a_report_that_is_already_done_is_not_done_again(
    client: TestClient, db_session: Session
) -> None:
    customer = create_user(db_session, email="done@example.com")
    upload = create_upload_row(session=db_session, customer=customer)
    report = QualityReport(upload_id=upload.id, status="DONE", pages=[], summary={"flagged": False})
    db_session.add(report)
    db_session.commit()

    assert not run_one(
        db_session,
        report_id=report.id,
        storage=client.app.state.storage,
        now=datetime.now(UTC),
    )
