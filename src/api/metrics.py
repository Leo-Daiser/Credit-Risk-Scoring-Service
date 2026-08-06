"""Prometheus metrics for HTTP and scoring operations."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "credit_risk_http_requests_total",
    "HTTP requests handled by the service.",
    ("method", "path", "status"),
)
HTTP_LATENCY = Histogram(
    "credit_risk_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "path"),
)
SCORE_DECISIONS = Counter(
    "credit_risk_score_decisions_total",
    "Scoring decisions returned by the model.",
    ("decision", "risk_band", "model_version"),
)
INPUT_QUALITY_WARNINGS = Counter(
    "credit_risk_input_quality_warnings_total",
    "Input-quality warnings produced during scoring.",
    ("warning",),
)


def record_scoring_result(result: dict[str, object]) -> None:
    SCORE_DECISIONS.labels(
        decision=str(result["decision"]),
        risk_band=str(result["risk_band"]),
        model_version=str(result["model_version"]),
    ).inc()
    quality = result.get("input_quality")
    if isinstance(quality, dict):
        warnings = quality.get("warnings", [])
        if isinstance(warnings, list):
            for warning in warnings:
                INPUT_QUALITY_WARNINGS.labels(warning=str(warning)).inc()
