"""FastAPI dependencies for model and database access."""

from functools import lru_cache
from secrets import compare_digest

from fastapi import Header, HTTPException, status

from src.core.config import settings
from src.public_profile.service import PublicProfileScoringService
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


@lru_cache(maxsize=1)
def _cached_public_profile_scoring_service() -> PublicProfileScoringService:
    return PublicProfileScoringService.from_path(
        settings.resolve_public_profile_model_path()
    )


def get_optional_public_profile_scoring_service() -> PublicProfileScoringService | None:
    """Use the public model when mounted and expose fallback explicitly otherwise."""
    try:
        return _cached_public_profile_scoring_service()
    except Exception:
        return None


def require_operator_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Fail closed for internal analytics/operator endpoints."""
    configured = settings.api_key
    if configured is None or not configured.get_secret_value().strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operator API key is not configured.",
        )
    supplied = x_api_key or ""
    if not compare_digest(supplied, configured.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing operator API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def require_local_demo_operator_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Expose demo catalog/debug routes only outside public deployments."""
    if settings.is_public:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    require_operator_api_key(x_api_key)
