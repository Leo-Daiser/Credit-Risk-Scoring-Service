"""Structured service logging with request correlation and no payload capture."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

CORRELATION_ID: ContextVar[str] = ContextVar("correlation_id", default="-")
SAFE_LOG_FIELDS = (
    "correlation_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "model_version",
    "decision",
    "risk_band",
    "logging_status",
)


def bind_correlation_id(value: str) -> Token[str]:
    return CORRELATION_ID.set(value)


def reset_correlation_id(token: Token[str]) -> None:
    CORRELATION_ID.reset(token)


class JsonLogFormatter(logging.Formatter):
    """Render an allowlisted JSON event suitable for container log collection."""

    def format(self, record: logging.LogRecord) -> str:
        event: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", CORRELATION_ID.get()),
        }
        for field in SAFE_LOG_FIELDS:
            if field == "correlation_id":
                continue
            value = getattr(record, field, None)
            if value is not None:
                event[field] = value
        if record.exc_info:
            event["exception"] = self.formatException(record.exc_info)
        return json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str)


class TextLogFormatter(logging.Formatter):
    """Human-readable formatter for local debugging with the same correlation field."""

    def format(self, record: logging.LogRecord) -> str:
        correlation_id = getattr(record, "correlation_id", CORRELATION_ID.get())
        base = super().format(record)
        return f"{base} correlation_id={correlation_id}"


def configure_logging(level: str, log_format: str) -> None:
    """Configure one root handler before the ASGI application starts serving."""
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            TextLogFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[handler],
        force=True,
    )
