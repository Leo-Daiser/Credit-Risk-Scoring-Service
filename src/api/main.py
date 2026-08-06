import logging
import time

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.api.metrics import HTTP_LATENCY, HTTP_REQUESTS
from src.api.routes import router
from src.core.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Calibrated credit-default risk scoring with explainability and audit logging.",
)
app.include_router(router)


@app.middleware("http")
async def observe_http_request(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(request.method, path, str(status_code)).inc()
        HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - started)


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
