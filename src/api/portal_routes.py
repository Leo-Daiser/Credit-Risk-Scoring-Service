"""Operator-facing API for the web cabinet and batch workflow."""

from __future__ import annotations

import csv
import io
import re
from datetime import timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.dependencies import get_scoring_service, require_api_key
from src.api.schemas import (
    BatchJobListResponse,
    BatchJobResponse,
    DashboardBatchSummary,
    DashboardResponse,
    DashboardScoringSummary,
    ModelInfoResponse,
    ScoringHistoryItem,
    ScoringHistoryResponse,
)
from src.core.config import settings
from src.db.models import BatchScoringJob, ScoringPrediction, ScoringRequest
from src.db.session import get_db
from src.services.batch_jobs import BatchUploadError, create_batch_job, utc_now
from src.services.scoring import ScoringService

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
ID_COLUMN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
HTTP_422_UNPROCESSABLE = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)


def history_item(request: ScoringRequest, prediction: ScoringPrediction) -> ScoringHistoryItem:
    return ScoringHistoryItem(
        request_id=request.request_id,
        received_at=request.received_at,
        default_probability=prediction.default_probability,
        decision=prediction.decision,
        decision_threshold=prediction.decision_threshold,
        risk_band=prediction.risk_band,
        model_version=request.model_version,
    )


def serialize_job(job: BatchScoringJob) -> BatchJobResponse:
    return BatchJobResponse.model_validate(job)


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    session: Session = Depends(get_db),
    service: ScoringService = Depends(get_scoring_service),
) -> DashboardResponse:
    since = utc_now() - timedelta(hours=24)
    total = int(session.scalar(select(func.count()).select_from(ScoringPrediction)) or 0)
    last_24h = int(
        session.scalar(
            select(func.count())
            .select_from(ScoringRequest)
            .where(ScoringRequest.received_at >= since)
        )
        or 0
    )
    approval_count = int(
        session.scalar(
            select(func.count())
            .select_from(ScoringPrediction)
            .where(ScoringPrediction.decision == "approve")
        )
        or 0
    )
    decided_count = int(
        session.scalar(
            select(func.count())
            .select_from(ScoringPrediction)
            .where(ScoringPrediction.decision.is_not(None))
        )
        or 0
    )
    mean_probability = session.scalar(
        select(func.avg(ScoringPrediction.default_probability))
    )
    risk_bands = {
        str(name): int(count)
        for name, count in session.execute(
            select(ScoringPrediction.risk_band, func.count())
            .group_by(ScoringPrediction.risk_band)
            .order_by(ScoringPrediction.risk_band)
        )
    }
    batch_counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
    for job_status, count in session.execute(
        select(BatchScoringJob.status, func.count()).group_by(BatchScoringJob.status)
    ):
        batch_counts[str(job_status)] = int(count)

    recent_rows = session.execute(
        select(ScoringRequest, ScoringPrediction)
        .join(ScoringPrediction, ScoringPrediction.request_id == ScoringRequest.request_id)
        .order_by(ScoringRequest.received_at.desc())
        .limit(6)
    ).all()
    return DashboardResponse(
        generated_at=utc_now(),
        model=ModelInfoResponse.model_validate(service.model_info()),
        scoring=DashboardScoringSummary(
            total=total,
            last_24h=last_24h,
            approval_rate=approval_count / decided_count if decided_count else None,
            mean_default_probability=(
                float(mean_probability) if mean_probability is not None else None
            ),
            risk_bands=risk_bands,
        ),
        batches=DashboardBatchSummary(**batch_counts),
        recent_decisions=[history_item(request, prediction) for request, prediction in recent_rows],
    )


@router.get("/scoring/history", response_model=ScoringHistoryResponse)
def scoring_history(
    decision: Literal["approve", "decline"] | None = Query(default=None),
    risk_band: str | None = Query(default=None, min_length=1, max_length=32),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> ScoringHistoryResponse:
    conditions = []
    if decision is not None:
        conditions.append(ScoringPrediction.decision == decision)
    if risk_band is not None:
        conditions.append(ScoringPrediction.risk_band == risk_band)

    total = int(
        session.scalar(
            select(func.count())
            .select_from(ScoringRequest)
            .join(ScoringPrediction, ScoringPrediction.request_id == ScoringRequest.request_id)
            .where(*conditions)
        )
        or 0
    )
    rows = session.execute(
        select(ScoringRequest, ScoringPrediction)
        .join(ScoringPrediction, ScoringPrediction.request_id == ScoringRequest.request_id)
        .where(*conditions)
        .order_by(ScoringRequest.received_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return ScoringHistoryResponse(
        items=[history_item(request, prediction) for request, prediction in rows],
        total=total,
    )


@router.post(
    "/batch/jobs",
    response_model=BatchJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_batch_job(
    file: UploadFile = File(...),
    id_column: str = Form(default="SK_ID_CURR"),
    session: Session = Depends(get_db),
) -> BatchJobResponse:
    if not ID_COLUMN_PATTERN.fullmatch(id_column):
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE,
            detail="id_column must be a valid flat table column name.",
        )
    filename = file.filename or "upload"
    try:
        job = create_batch_job(
            session,
            source=file.file,
            original_filename=filename,
            id_column=id_column,
        )
    except BatchUploadError as exc:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE,
            detail=str(exc),
        ) from exc
    finally:
        file.file.close()
    return serialize_job(job)


@router.get("/batch/jobs", response_model=BatchJobListResponse)
def list_batch_jobs(
    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> BatchJobListResponse:
    total = int(session.scalar(select(func.count()).select_from(BatchScoringJob)) or 0)
    jobs = session.scalars(
        select(BatchScoringJob)
        .order_by(BatchScoringJob.created_at.desc())
        .limit(limit)
    ).all()
    return BatchJobListResponse(items=[serialize_job(job) for job in jobs], total=total)


@router.get("/batch/jobs/{job_id}", response_model=BatchJobResponse)
def get_batch_job(job_id: str, session: Session = Depends(get_db)) -> BatchJobResponse:
    job = session.scalar(
        select(BatchScoringJob).where(BatchScoringJob.job_id == job_id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch job not found.")
    return serialize_job(job)


@router.get("/batch/jobs/{job_id}/result", response_class=FileResponse)
def download_batch_result(job_id: str, session: Session = Depends(get_db)) -> FileResponse:
    job = session.scalar(
        select(BatchScoringJob).where(BatchScoringJob.job_id == job_id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch job not found.")
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Batch result is not ready.",
        )
    result_path = Path(job.output_path).resolve()
    output_root = Path(settings.batch_output_dir).resolve()
    if not result_path.is_relative_to(output_root) or not result_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Batch result artifact is unavailable.",
        )
    result_name = f"{Path(job.original_filename).stem}-scores.csv"
    return FileResponse(result_path, media_type="text/csv", filename=result_name)


@router.get("/batch/template.csv")
def download_batch_template(
    service: ScoringService = Depends(get_scoring_service),
) -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["SK_ID_CURR", *service.bundle.feature_names])
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="scoring-template.csv"'},
    )
