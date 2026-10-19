"""Tests for the worker loop.

The worker must keep going when one job fails, and it must report what
each job did.
"""

from datetime import UTC, datetime

from app.gateways.storage import MemoryStorage
from app.jobs import scheduler
from sqlalchemy.orm import Session
from tests.factories import RecordingGateway

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class BorrowedSession:
    """A context manager that yields a session without closing it.

    The test session is owned by the fixture and rolls back at the end of
    the test, so the worker must not close it.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *args: object) -> None:
        return None


def test_run_once_reports_every_job(db_session: Session) -> None:
    results = scheduler.run_once(
        now=NOW,
        session_factory=lambda: BorrowedSession(db_session),
        storage=MemoryStorage(),
        gateway=RecordingGateway(),
    )

    assert set(results) == {
        "expire_orders",
        "auto_reject",
        "expire_no_shows",
        "process_refunds",
        "purge_files",
    }
    assert all(count == 0 for count in results.values())


def test_a_failing_job_does_not_stop_the_others(db_session: Session, monkeypatch) -> None:
    def broken(session: Session, *, now: datetime) -> int:
        raise RuntimeError("job is broken")

    monkeypatch.setattr(scheduler.expire_orders, "run", broken)

    results = scheduler.run_once(
        now=NOW,
        session_factory=lambda: BorrowedSession(db_session),
        storage=MemoryStorage(),
        gateway=RecordingGateway(),
    )

    assert results["expire_orders"] == 0
    assert "auto_reject" in results
    assert "purge_files" in results
