"""Durable batch-upload storage and worker orchestration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings
from src.db.models import BatchScoringJob
from src.services.batch import score_batch_file
from src.services.scoring import ScoringService

logger = logging.getLogger(__name__)
ALLOWED_BATCH_SUFFIXES = {".csv": "csv", ".parquet": "parquet", ".pq": "parquet"}
COPY_CHUNK_BYTES = 1024 * 1024


class BatchUploadError(ValueError):
    """Raised when an uploaded batch file violates the public contract."""


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def batch_paths(job_id: str, original_filename: str) -> tuple[Path, Path, str]:
    safe_name = Path(original_filename).name
    suffix = Path(safe_name).suffix.lower()
    input_format = ALLOWED_BATCH_SUFFIXES.get(suffix)
    if input_format is None:
        raise BatchUploadError("Only CSV and parquet batch files are supported.")

    input_root = Path(settings.batch_storage_dir)
    output_root = Path(settings.batch_output_dir)
    input_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    return input_root / f"{job_id}{suffix}", output_root / f"{job_id}.csv", input_format


def save_limited_upload(source: BinaryIO, destination: Path, max_bytes: int) -> int:
    """Stream an upload to disk without buffering an unbounded payload in memory."""
    bytes_written = 0
    try:
        with destination.open("xb") as target:
            while chunk := source.read(COPY_CHUNK_BYTES):
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise BatchUploadError(
                        f"Uploaded file exceeds the {max_bytes}-byte limit."
                    )
                target.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if bytes_written == 0:
        destination.unlink(missing_ok=True)
        raise BatchUploadError("Uploaded batch file is empty.")
    return bytes_written


def create_batch_job(
    session: Session,
    *,
    source: BinaryIO,
    original_filename: str,
    id_column: str,
) -> BatchScoringJob:
    job_id = str(uuid4())
    input_path, output_path, input_format = batch_paths(job_id, original_filename)
    size = save_limited_upload(source, input_path, settings.batch_max_upload_bytes)
    job = BatchScoringJob(
        job_id=job_id,
        original_filename=Path(original_filename).name[:255],
        input_format=input_format,
        id_column=id_column,
        input_path=str(input_path),
        output_path=str(output_path),
        file_size_bytes=size,
        status="queued",
        rows_processed=0,
    )
    try:
        session.add(job)
        session.commit()
        session.refresh(job)
    except Exception:
        session.rollback()
        input_path.unlink(missing_ok=True)
        raise
    return job


def claim_next_job(session: Session) -> str | None:
    statement = (
        select(BatchScoringJob)
        .where(BatchScoringJob.status == "queued")
        .order_by(BatchScoringJob.created_at, BatchScoringJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = session.scalar(statement)
    if job is None:
        session.rollback()
        return None
    job.status = "running"
    job.started_at = utc_now()
    job.error_message = None
    session.commit()
    return job.job_id


def recover_stale_jobs(session: Session, *, older_than_minutes: int = 30) -> int:
    """Requeue jobs abandoned by an interrupted worker process."""
    cutoff = utc_now() - timedelta(minutes=older_than_minutes)
    result = session.execute(
        update(BatchScoringJob)
        .where(
            BatchScoringJob.status == "running",
            BatchScoringJob.started_at < cutoff,
        )
        .values(status="queued", started_at=None)
    )
    session.commit()
    return int(result.rowcount or 0)


def process_claimed_job(
    session_factory: sessionmaker,
    job_id: str,
    service: ScoringService,
) -> None:
    with session_factory() as session:
        job = session.scalar(
            select(BatchScoringJob).where(BatchScoringJob.job_id == job_id)
        )
        if job is None or job.status != "running":
            return
        input_path = Path(job.input_path)
        output_path = Path(job.output_path)
        try:
            summary = score_batch_file(
                input_path,
                output_path,
                service,
                id_column=job.id_column,
                max_rows=settings.batch_max_rows,
            )
            rows_scored = int(summary["rows_scored"])
            job.status = "completed"
            job.rows_total = rows_scored
            job.rows_processed = rows_scored
            job.model_version = str(summary["model_version"])
            job.summary_json = summary
            job.completed_at = utc_now()
            session.commit()
            if not settings.batch_retain_inputs:
                input_path.unlink(missing_ok=True)
            logger.info(
                "batch_job_completed",
                extra={"job_id": job_id, "rows_scored": rows_scored},
            )
        except Exception as exc:
            session.rollback()
            failed = session.scalar(
                select(BatchScoringJob).where(BatchScoringJob.job_id == job_id)
            )
            if failed is not None:
                failed.status = "failed"
                failed.error_message = str(exc)[:2000]
                failed.completed_at = utc_now()
                session.commit()
            output_path.unlink(missing_ok=True)
            logger.exception("batch_job_failed", extra={"job_id": job_id})
