from fastapi import APIRouter
from src.api.schemas import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", service="credit-risk-scoring")