from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.dependencies import get_scoring_service
from src.api.schemas import (
    HealthResponse,
    ModelInfoResponse,
    ReadinessResponse,
    ScoreRequest,
    ScoreResponse,
)
from src.core.config import settings
from src.db.session import get_db
from src.services.scoring import (
    DuplicateRequestError,
    ScoringService,
    persist_scoring_result,
)

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", service="credit-risk-scoring")


@router.get("/model_info", response_model=ModelInfoResponse)
def model_info(
    service: ScoringService = Depends(get_scoring_service),
) -> ModelInfoResponse:
    return ModelInfoResponse.model_validate(service.model_info())


@router.get("/ready", response_model=ReadinessResponse)
def readiness(
    service: ScoringService = Depends(get_scoring_service),
    session: Session = Depends(get_db),
) -> ReadinessResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return ReadinessResponse(
        status="ready",
        model_version=service.bundle.metadata["model_version"],
        database="ok",
    )


@router.post("/score", response_model=ScoreResponse)
def score(
    payload: ScoreRequest,
    service: ScoringService = Depends(get_scoring_service),
    session: Session = Depends(get_db),
) -> ScoreResponse:
    try:
        result = service.score(payload.features, request_id=payload.request_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if not settings.inference_logging_enabled:
        result["logging_status"] = "disabled"
        return ScoreResponse.model_validate(result)

    try:
        persist_scoring_result(session, payload.features, result)
        result["logging_status"] = "persisted"
    except DuplicateRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        if settings.database_required:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Scoring succeeded, but the required inference log could not be persisted.",
            ) from exc
        result["logging_status"] = "failed"
    return ScoreResponse.model_validate(result)
