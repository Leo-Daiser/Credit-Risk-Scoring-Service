import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_optional_public_profile_scoring_service,
    get_optional_scoring_service,
    get_scoring_service,
    require_operator_api_key,
)
from src.api.metrics import record_scoring_result
from src.api.schemas import (
    FeatureSchemaResponse,
    HealthResponse,
    ModelInfoResponse,
    ReadinessResponse,
    ScoreRequest,
    ScoreResponse,
)
from src.core.config import settings
from src.db.session import get_db
from src.offers.repository import OfferRepository
from src.public_profile.service import PublicProfileScoringService
from src.services.scoring import (
    DuplicateRequestError,
    ScoringService,
    persist_scoring_result,
)

router = APIRouter()
logger = logging.getLogger(__name__)
HTTP_422_UNPROCESSABLE = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)


@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", service="credit-risk-scoring")


@router.get("/model_info", response_model=ModelInfoResponse)
def model_info(
    _: None = Depends(require_operator_api_key),
    service: ScoringService = Depends(get_scoring_service),
) -> ModelInfoResponse:
    return ModelInfoResponse.model_validate(service.model_info())


@router.get("/feature_schema", response_model=FeatureSchemaResponse)
def feature_schema(
    _: None = Depends(require_operator_api_key),
    service: ScoringService = Depends(get_scoring_service),
) -> FeatureSchemaResponse:
    schema = service.bundle.feature_schema
    return FeatureSchemaResponse(
        model_version=service.bundle.metadata["model_version"],
        feature_count=len(service.bundle.feature_names),
        numeric_features=list(schema.get("numeric_features", [])),
        categorical_features=list(schema.get("categorical_features", [])),
        required_features=service.required_features,
        min_feature_coverage=service.min_feature_coverage,
    )


@router.get("/ready", response_model=ReadinessResponse)
def readiness(
    service: ScoringService | None = Depends(get_optional_scoring_service),
    public_service: PublicProfileScoringService | None = Depends(
        get_optional_public_profile_scoring_service
    ),
    session: Session = Depends(get_db),
) -> ReadinessResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    model_ready = service is not None
    if settings.model_bundle_required and not model_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required production model is unavailable.",
        )
    if settings.public_profile_model_required and public_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required public profile model is unavailable.",
        )
    catalog_ready = bool(OfferRepository(session).list_active())
    warnings = []
    if not model_ready:
        warnings.append("model_bundle_unavailable_operator_scoring_disabled")
    if public_service is None:
        warnings.append("public_profile_model_unavailable_rules_fallback_active")
    offer_ranker_available = Path(settings.offer_ranker_model_path).is_file()
    if settings.offer_ranker_mode == "ml" and not offer_ranker_available:
        warnings.append("offer_ranker_unavailable_rules_fallback_active")
    if not catalog_ready:
        warnings.append("offer_catalog_empty")
    return ReadinessResponse(
        status="ready" if not warnings else "degraded",
        model_version=service.bundle.metadata["model_version"] if service else None,
        database="ok",
        model_bundle_ready=model_ready,
        full_model_available=model_ready,
        public_model_available=public_service is not None,
        public_model_version=(
            public_service.bundle.metadata["model_version"] if public_service else None
        ),
        offer_ranker_available=offer_ranker_available,
        fallback_only_mode=public_service is None,
        commercial_matching_ready=catalog_ready,
        warnings=warnings,
    )


@router.post("/score", response_model=ScoreResponse)
def score(
    payload: ScoreRequest,
    _: None = Depends(require_operator_api_key),
    service: ScoringService = Depends(get_scoring_service),
    session: Session = Depends(get_db),
) -> ScoreResponse:
    try:
        result = service.score(payload.features, request_id=payload.request_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE,
            detail=str(exc),
        ) from exc
    if not settings.inference_logging_enabled:
        result["logging_status"] = "disabled"
    else:
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
                    detail=(
                        "Scoring succeeded, but the required inference log could not be persisted."
                    ),
                ) from exc
            result["logging_status"] = "failed"
    record_scoring_result(result)
    logger.info(
        "score_completed",
        extra={
            "model_version": result["model_version"],
            "decision": result["decision"],
            "risk_band": result["risk_band"],
            "logging_status": result["logging_status"],
        },
    )
    return ScoreResponse.model_validate(result)
