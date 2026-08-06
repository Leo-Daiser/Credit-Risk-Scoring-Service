import logging

from fastapi import FastAPI

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
