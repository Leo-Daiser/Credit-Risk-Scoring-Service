"""PostgreSQL-backed batch-scoring worker process."""

from __future__ import annotations

import logging
import signal
from threading import Event

from src.core.config import settings
from src.core.logging import configure_logging
from src.db.session import SessionLocal
from src.services.batch_jobs import claim_next_job, process_claimed_job, recover_stale_jobs
from src.services.scoring import ScoringService

logger = logging.getLogger(__name__)
stop_event = Event()


def request_shutdown(signum, frame) -> None:  # noqa: ARG001
    stop_event.set()


def run() -> None:
    configure_logging(settings.log_level, settings.log_format)
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    service = ScoringService.from_path(
        settings.resolve_model_bundle_path(),
        top_reason_codes=settings.top_reason_codes,
    )
    with SessionLocal() as session:
        recovered = recover_stale_jobs(session)
    logger.info("batch_worker_started", extra={"recovered_jobs": recovered})

    while not stop_event.is_set():
        with SessionLocal() as session:
            job_id = claim_next_job(session)
        if job_id is None:
            stop_event.wait(settings.batch_worker_poll_seconds)
            continue
        process_claimed_job(SessionLocal, job_id, service)

    logger.info("batch_worker_stopped")


if __name__ == "__main__":
    run()
