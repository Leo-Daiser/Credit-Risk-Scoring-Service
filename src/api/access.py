"""Central deployment access classification for HTTP endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AccessClass(StrEnum):
    PUBLIC = "public"
    BFF_ONLY = "bff_only"
    OPERATOR_ONLY = "operator_only"
    PARTNER_ONLY = "partner_only"
    PLATFORM_ONLY = "platform_only"
    LOCAL_DEMO_ONLY = "local_demo_only"


@dataclass(frozen=True)
class EndpointAccess:
    method: str
    path: str
    access: AccessClass
    purpose: str


ENDPOINT_ACCESS_MATRIX = (
    EndpointAccess("GET", "/health", AccessClass.PLATFORM_ONLY, "Liveness probe"),
    EndpointAccess("GET", "/ready", AccessClass.PLATFORM_ONLY, "Readiness probe"),
    EndpointAccess("GET", "/metrics", AccessClass.PLATFORM_ONLY, "Prometheus scrape"),
    EndpointAccess("POST", "/v1/profile/score", AccessClass.PUBLIC, "Privacy-light profile"),
    EndpointAccess("POST", "/v1/offers/match", AccessClass.PUBLIC, "Offer matching"),
    EndpointAccess("POST", "/v1/offers/{offer_id}/click", AccessClass.PUBLIC, "Tracked redirect"),
    EndpointAccess("POST", "/v1/analytics/public-event", AccessClass.PUBLIC, "Safe public event"),
    EndpointAccess("POST", "/v1/partner/postback", AccessClass.PARTNER_ONLY, "HMAC postback"),
    EndpointAccess("POST", "/score", AccessClass.OPERATOR_ONLY, "Raw model scoring"),
    EndpointAccess("GET", "/model_info", AccessClass.OPERATOR_ONLY, "Model metadata"),
    EndpointAccess("GET", "/feature_schema", AccessClass.OPERATOR_ONLY, "Model contract"),
    EndpointAccess("*", "/v1/dashboard", AccessClass.BFF_ONLY, "Operator dashboard"),
    EndpointAccess("*", "/v1/scoring/history", AccessClass.BFF_ONLY, "Decision history"),
    EndpointAccess("*", "/v1/batch/**", AccessClass.BFF_ONLY, "Batch scoring"),
    EndpointAccess(
        "GET", "/v1/analytics/commercial-summary", AccessClass.OPERATOR_ONLY, "Analytics"
    ),
    EndpointAccess(
        "GET", "/v1/analytics/segment-opportunities", AccessClass.OPERATOR_ONLY, "Segments"
    ),
    EndpointAccess("GET", "/v1/analytics/event-debug", AccessClass.OPERATOR_ONLY, "Events"),
    EndpointAccess("GET", "/v1/offers/quality-report", AccessClass.OPERATOR_ONLY, "Offer quality"),
    EndpointAccess("GET", "/v1/offers", AccessClass.LOCAL_DEMO_ONLY, "Demo catalog debug"),
)
