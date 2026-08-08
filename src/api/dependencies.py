"""FastAPI dependencies for model and database access."""

from functools import lru_cache
from secrets import compare_digest

from fastapi import Header, HTTPException, status

from src.core.config import settings
from src.services.scoring import ScoringService


@lru_cache(maxsize=1)
def _cached_scoring_service() -> ScoringService:
    return ScoringService.from_path(
        settings.resolve_model_bundle_path(),
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


def get_optional_scoring_service() -> ScoringService | None:
    """Return a model when available without breaking commercial fallback behavior."""
    try:
        return _cached_scoring_service()
    except Exception:
        return None


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Require an API key when one is configured for the deployment."""
    configured = settings.api_key
    if configured is None:
        return
    supplied = x_api_key or ""
    if not compare_digest(supplied, configured.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
