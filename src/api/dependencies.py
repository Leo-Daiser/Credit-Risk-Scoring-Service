"""FastAPI dependencies for model and database access."""

from functools import lru_cache

from fastapi import HTTPException, status

from src.core.config import settings
from src.services.scoring import ScoringService


@lru_cache(maxsize=1)
def _cached_scoring_service() -> ScoringService:
    return ScoringService.from_path(
        settings.model_bundle_path,
        top_reason_codes=settings.top_reason_codes,
    )


def get_scoring_service() -> ScoringService:
    try:
        return _cached_scoring_service()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Production model is unavailable: {exc}",
        ) from exc
