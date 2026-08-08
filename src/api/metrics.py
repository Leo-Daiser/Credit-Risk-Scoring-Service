"""Prometheus metrics for HTTP and scoring operations."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

from prometheus_client import Counter, Gauge, Histogram

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
OFFER_MATCH_REQUESTS = Counter(
    "credit_risk_offer_match_requests_total", "Commercial offer match requests."
)
OFFER_IMPRESSIONS = Counter(
    "credit_risk_offer_impressions_total", "Offer impressions.", ("offer_id",)
)
OFFER_CLICKS = Counter("credit_risk_offer_clicks_total", "Offer clicks.", ("offer_id",))
OFFER_CLICK_THROUGH_RATE = Gauge(
    "credit_risk_offer_click_through_rate",
    "Process-local click-through rate by offer.",
    ("offer_id",),
)
OFFER_POSTBACKS = Counter(
    "credit_risk_partner_postbacks_total", "Partner outcomes.", ("offer_id", "status")
)
NO_ELIGIBLE_OFFERS = Counter(
    "credit_risk_no_eligible_offers_total", "Matches with no eligible offers."
)
ELIGIBLE_OFFERS = Histogram(
    "credit_risk_eligible_offers_per_request", "Eligible offers per match request."
)
COMMERCIAL_RISK_BANDS = Counter(
    "credit_risk_commercial_profile_risk_band_total", "Commercial profile risk bands.", ("band",)
)
COMMERCIAL_PTI_BANDS = Counter(
    "credit_risk_commercial_profile_pti_band_total", "Commercial profile PTI bands.", ("band",)
)
OFFER_RANKER_MODE = Gauge(
    "credit_risk_offer_ranker_mode", "Active ranker mode (one-hot).", ("mode",)
)
POSTBACK_SIGNATURE_FAILURES = Counter(
    "credit_risk_postback_signature_failures_total", "Invalid partner postback signatures."
)
REDIRECT_FAILURES = Counter(
    "credit_risk_offer_redirect_failures_total", "Failed offer redirect creations."
)

_OFFER_COUNTS_LOCK = Lock()
_OFFER_IMPRESSION_COUNTS: defaultdict[str, int] = defaultdict(int)
_OFFER_CLICK_COUNTS: defaultdict[str, int] = defaultdict(int)


def record_offer_impression(offer_id: int) -> None:
    label = str(offer_id)
    OFFER_IMPRESSIONS.labels(label).inc()
    with _OFFER_COUNTS_LOCK:
        _OFFER_IMPRESSION_COUNTS[label] += 1
        OFFER_CLICK_THROUGH_RATE.labels(label).set(
            _OFFER_CLICK_COUNTS[label] / _OFFER_IMPRESSION_COUNTS[label]
        )


def record_offer_click(offer_id: int) -> None:
    label = str(offer_id)
    OFFER_CLICKS.labels(label).inc()
    with _OFFER_COUNTS_LOCK:
        _OFFER_CLICK_COUNTS[label] += 1
        impressions = _OFFER_IMPRESSION_COUNTS[label]
        OFFER_CLICK_THROUGH_RATE.labels(label).set(
            _OFFER_CLICK_COUNTS[label] / impressions if impressions else 0.0
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
