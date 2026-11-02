from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Lock

from app.gateways.storage import MemoryStorage
from app.jobs import analyze_quality
from app.models import QualityReport, Upload, User
from app.services.quality_service import ANALYSIS_TIMEOUT_SECONDS
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker
from tests.factories import create_upload_row, create_user
from tests.fixtures.pdf_files import make_pdf

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
RECOVERY_SECONDS = ANALYSIS_TIMEOUT_SECONDS * 2


def _running_report(session: Session, *, started_at: datetime) -> tuple[QualityReport, str]:
    customer = create_user(session, email=f"quality-{started_at.timestamp()}@example.com")
    upload = create_upload_row(session, customer=customer)
    report = QualityReport(
        upload_id=upload.id,
        status="RUNNING",
        pages=[],
        summary={},
        algorithm_version="1",
        started_at=started_at,
    )
    session.add(report)
    session.commit()
    return report, upload.file_key


def test_a_stale_running_quality_report_is_recovered(db_session: Session, tmp_path) -> None:
    report, file_key = _running_report(
        db_session,
        started_at=NOW - timedelta(seconds=RECOVERY_SECONDS + 1),
    )
    pdf = make_pdf(tmp_path / "recover.pdf")
    storage = MemoryStorage()
    storage.objects[file_key] = pdf.read_bytes()

    recovered = analyze_quality.run(db_session, storage=storage, now=NOW)

    assert recovered == 1
    db_session.refresh(report)
    assert report.status == "DONE"
    assert report.started_at == NOW
    assert report.completed_at == NOW


def test_a_recent_running_quality_report_is_not_claimed_twice(db_session: Session) -> None:
    report, _file_key = _running_report(
        db_session,
        started_at=NOW - timedelta(seconds=RECOVERY_SECONDS - 1),
    )

    recovered = analyze_quality.run(db_session, storage=MemoryStorage(), now=NOW)

    assert recovered == 0
    db_session.refresh(report)
    assert report.status == "RUNNING"


def test_two_workers_do_not_analyse_a_report_claimed_after_batch_locks_release(
    engine, tmp_path: Path
) -> None:
    suffix = str(datetime.now(UTC).timestamp())
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as seed_session:
        first_customer = create_user(seed_session, email=f"quality-a-{suffix}@example.com")
        second_customer = create_user(seed_session, email=f"quality-b-{suffix}@example.com")
        first_upload = create_upload_row(seed_session, customer=first_customer)
        second_upload = create_upload_row(seed_session, customer=second_customer)
        first_report = QualityReport(
            upload_id=first_upload.id,
            status="PENDING",
            pages=[],
            summary={},
            algorithm_version="1",
            created_at=NOW,
        )
        second_report = QualityReport(
            upload_id=second_upload.id,
            status="PENDING",
            pages=[],
            summary={},
            algorithm_version="1",
            created_at=NOW + timedelta(microseconds=1),
        )
        seed_session.add_all([first_report, second_report])
        seed_session.commit()
        first_report_id, second_report_id = first_report.id, second_report.id
        first_upload_key, second_upload_key = first_upload.file_key, second_upload.file_key
        user_ids = [first_customer.id, second_customer.id]
        upload_ids = [first_upload.id, second_upload.id]

    pdf = make_pdf(tmp_path / "concurrent.pdf")
    first_entered = Event()
    second_entered = Event()
    release_first = Event()
    release_second = Event()
    counts: dict[str, int] = {first_upload_key: 0, second_upload_key: 0}
    counts_lock = Lock()

    class CoordinatedStorage(MemoryStorage):
        def download_to_path(self, key: str, path: Path) -> None:
            with counts_lock:
                counts[key] += 1
                call_count = counts[key]
            if key == first_upload_key:
                first_entered.set()
                assert release_first.wait(timeout=10)
            elif key == second_upload_key:
                if call_count == 1:
                    second_entered.set()
                    assert release_second.wait(timeout=10)
            super().download_to_path(key, path)

    storage = CoordinatedStorage()
    storage.objects[first_upload_key] = pdf.read_bytes()
    storage.objects[second_upload_key] = pdf.read_bytes()

    def run_job() -> int:
        with factory() as session:
            return analyze_quality.run(session, storage=storage, now=NOW)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_worker = executor.submit(run_job)
            assert first_entered.wait(timeout=10)
            second_worker = executor.submit(run_job)
            assert second_entered.wait(timeout=10)
            release_first.set()
            assert first_worker.result(timeout=10) == 1
            with counts_lock:
                assert counts[second_upload_key] == 1
            release_second.set()
            assert second_worker.result(timeout=10) == 1

        with factory() as verify_session:
            statuses = list(
                verify_session.scalars(
                    select(QualityReport.status).where(
                        QualityReport.id.in_([first_report_id, second_report_id])
                    )
                )
            )
            assert statuses == ["DONE", "DONE"]
    finally:
        release_first.set()
        release_second.set()
        with factory.begin() as cleanup:
            cleanup.execute(delete(QualityReport).where(QualityReport.upload_id.in_(upload_ids)))
            cleanup.execute(delete(Upload).where(Upload.id.in_(upload_ids)))
            cleanup.execute(delete(User).where(User.id.in_(user_ids)))
