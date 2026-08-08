import logging
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.api.commercial_routes import router as commercial_router
from src.api.metrics import HTTP_LATENCY, HTTP_REQUESTS
from src.api.operator_routes import router as operator_router
from src.api.portal_routes import router as portal_router
from src.api.routes import router
from src.core.config import settings
from src.core.logging import bind_correlation_id, configure_logging, reset_correlation_id

configure_logging(settings.log_level, settings.log_format)
logger = logging.getLogger(__name__)
CORRELATION_HEADER = "X-Correlation-ID"
CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

if settings.app_env.lower() in {"production", "prod", "public"} and (
    settings.api_key is None or not settings.api_key.get_secret_value().strip()
):
    logger.warning(
        "public_deployment_without_api_key",
        extra={"operator_endpoints_available": not settings.operator_api_key_required},
    )

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Calibrated credit-default risk scoring with explainability and audit logging.",
)
app.include_router(router)
app.include_router(portal_router)
app.include_router(commercial_router)
app.include_router(operator_router)


@app.middleware("http")
async def observe_http_request(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    supplied_correlation_id = request.headers.get(CORRELATION_HEADER, "").strip()
    correlation_id = (
        supplied_correlation_id
        if CORRELATION_ID_PATTERN.fullmatch(supplied_correlation_id)
        else str(uuid4())
    )
    token = bind_correlation_id(correlation_id)
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers[CORRELATION_HEADER] = correlation_id
        return response
    finally:
        duration_seconds = time.perf_counter() - started
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(request.method, path, str(status_code)).inc()
        HTTP_LATENCY.labels(request.method, path).observe(duration_seconds)
        logger.info(
            "http_request_completed",
            extra={
                "method": request.method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_seconds * 1000.0, 3),
            },
        )
        reset_correlation_id(token)


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
