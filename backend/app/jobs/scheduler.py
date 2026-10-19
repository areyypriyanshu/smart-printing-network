import logging
import signal
import threading
from pathlib import Path
from types import FrameType

from app.logging import setup_logging

logger = logging.getLogger(__name__)

HEARTBEAT_PATH = Path("/tmp/spn-worker-heartbeat")
LOOP_SECONDS = 30

_stop = threading.Event()


def _request_stop(signum: int, frame: FrameType | None) -> None:
    _stop.set()


def main() -> None:
    setup_logging()
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    logger.info("worker started; no jobs registered yet")
    while not _stop.is_set():
        HEARTBEAT_PATH.touch()
        _stop.wait(LOOP_SECONDS)
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
