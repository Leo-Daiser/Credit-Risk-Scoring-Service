from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalyticsTimeWindow(BaseModel):
    days: int
    start: datetime
    end: datetime


class CommercialSummaryMetrics(BaseModel):
    total_profile_scores: int = 0
    total_match_requests: int = 0
    total_offer_impressions: int = 0
    total_offer_clicks: int = 0
    ctr_overall: float = 0.0
    no_eligible_offers_rate: float = 0.0
    postback_conversion_rate: float = 0.0
    approval_rate: float = 0.0
    issued_rate: float = 0.0
    estimated_revenue: float = 0.0
    ctr_by_offer: dict[str, float] = Field(default_factory=dict)
    ctr_by_risk_band: dict[str, float] = Field(default_factory=dict)
    ctr_by_pti_band: dict[str, float] = Field(default_factory=dict)
    revenue_by_offer: dict[str, float] = Field(default_factory=dict)
    revenue_by_risk_band: dict[str, float] = Field(default_factory=dict)
    top_offers_by_clicks: list[int] = Field(default_factory=list)
    top_offers_by_issued: list[int] = Field(default_factory=list)
    stale_offer_ids: list[int] = Field(default_factory=list)
    high_demand_no_offer_segments: list[str] = Field(default_factory=list)


class OfferAnalyticsMetric(BaseModel):
    offer_id: int
    product_name: str
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    postback_clicks: int = 0
    approvals: int = 0
    issued: int = 0
    approval_rate: float = 0.0
    issued_rate: float = 0.0
    estimated_revenue: float = 0.0
    expected_revenue_proxy: float = 0.0
    revenue_estimate_source: str = "conservative_prior"
    revenue_estimate_confidence: str = "low"


class SegmentAnalyticsMetric(BaseModel):
    risk_band: str
    pti_band: str
    requests: int = 0
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    no_eligible_requests: int = 0
    revenue: float = 0.0


class ExperimentAnalyticsMetric(BaseModel):
    variant: str
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    approvals: int = 0
    issued: int = 0


class CommercialAnalyticsResponse(BaseModel):
    summary: CommercialSummaryMetrics
    offer_metrics: list[OfferAnalyticsMetric]
    segment_metrics: list[SegmentAnalyticsMetric]
    experiment_metrics: list[ExperimentAnalyticsMetric]
    warnings: list[str]
    time_window: AnalyticsTimeWindow


QualityRecommendation = Literal[
    "keep",
    "review_copy",
    "review_rules",
    "pause_candidate",
    "needs_real_partner_data",
    "missing_disclosure",
]


class OfferQualityItem(BaseModel):
    offer_id: int
    product_name: str
    bank_id: str
    status: str
    quality_flags: list[str]
    impressions: int
    clicks: int
    ctr: float
    postback_approval_rate: float
    postback_issued_rate: float
    estimated_revenue: float
    expected_revenue_proxy: float
    recommendation: QualityRecommendation


class OfferQualitySummary(BaseModel):
    active_offers: int = 0
    inactive_offers: int = 0
    zero_impression_offers: int = 0
    impressions_without_clicks: int = 0


class OfferQualityReport(BaseModel):
    summary: OfferQualitySummary
    offers: list[OfferQualityItem]
    warnings: list[str]
    time_window: AnalyticsTimeWindow


SegmentRecommendation = Literal[
    "add_low_amount_offer",
    "add_refinance_offer",
    "add_self_employed_offer",
    "add_bad_credit_history_offer",
    "tighten_disclaimers",
    "no_action",
]


class SegmentOpportunity(BaseModel):
    segment_key: str
    segment_value: str
    requests: int
    eligible_offer_rate: float
    click_rate: float
    approval_rate: float | None
    estimated_lost_clicks: float
    recommendation: SegmentRecommendation


class SegmentOpportunityResponse(BaseModel):
    opportunities: list[SegmentOpportunity]
    warnings: list[str]
    time_window: AnalyticsTimeWindow


class EventDebugItem(BaseModel):
    event_type: str
    click_id: str | None
    offer_id: int | None
    status: str | None
    hmac_validation_status: str | None
    experiment_variant: str
    occurred_at: datetime


class EventDebugResponse(BaseModel):
    events: list[EventDebugItem]
    raw_payloads_exposed: bool = False
