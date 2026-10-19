"""The worker process.

Runs the four periodic jobs. The state of every job lives in Postgres,
so the worker holds nothing in memory between runs: if it is restarted it
simply picks up where the database says it left off, and a second worker
running at the same time is safe because the jobs lock the rows they
claim and update them conditionally.

The heartbeat file is what the container healthcheck watches. It is
touched on every loop, even when a job fails, so one broken job does not
look like a dead worker.
"""

import logging
import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.gateways.payments import PaymentGateway, build_payment_gateway
from app.gateways.storage import S3Storage, Storage
from app.jobs import auto_reject, expire_orders, process_refunds, purge_files
from app.logging import setup_logging

logger = logging.getLogger(__name__)

HEARTBEAT_PATH = Path("/tmp/spn-worker-heartbeat")
LOOP_SECONDS = 30

_stop = threading.Event()


def _request_stop(signum: int, frame: FrameType | None) -> None:
    _stop.set()


def run_once(
    *,
    now: datetime | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    storage: Storage | None = None,
    gateway: PaymentGateway | None = None,
) -> dict[str, int]:
    """Run every job once and report how much each one did.

    Each job gets its own session, so a job that fails cannot leave an
    open transaction behind for the next one. A failing job is logged and
    skipped; the others still run.
    """
    current = datetime.now(UTC) if now is None else now
    settings = get_settings()
    if storage is None:
        storage = S3Storage(
            endpoint_url=settings.s3_endpoint_url or None,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
        )
    if gateway is None:
        gateway = build_payment_gateway(settings)

    jobs: list[tuple[str, Callable[[Session], int]]] = [
        ("expire_orders", lambda session: expire_orders.run(session, now=current)),
        ("auto_reject", lambda session: auto_reject.run(session, now=current)),
        (
            "process_refunds",
            lambda session: process_refunds.run(session, now=current, gateway=gateway),
        ),
        (
            "purge_files",
            lambda session: purge_files.run(session, storage=storage, now=current),
        ),
    ]

    results: dict[str, int] = {}
    for name, job in jobs:
        try:
            with session_factory() as session:
                results[name] = job(session)
        except Exception as exc:
            logger.error("job_failed", extra={"job": name, "reason": str(exc)})
            results[name] = 0

    return results


def main() -> None:
    setup_logging()
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    logger.info("worker started")
    while not _stop.is_set():
        HEARTBEAT_PATH.touch()
        results = run_once()
        logger.info("jobs_finished", extra=results)
        _stop.wait(LOOP_SECONDS)
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
