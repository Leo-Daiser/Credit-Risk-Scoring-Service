from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import BankOffer
from src.offers.analytics import CommercialAnalyticsService
from src.offers.operator_schemas import (
    OfferQualityItem,
    OfferQualityReport,
    OfferQualitySummary,
    QualityRecommendation,
)


def _rules_are_broad(offer: BankOffer) -> bool:
    return (
        len(offer.allowed_age_bands) >= 5
        and len(offer.allowed_employment_types) >= 6
        and len(offer.allowed_credit_history_bands) >= 5
        and len(offer.risk_band_policy) >= 4
    )


def _rules_are_narrow(offer: BankOffer) -> bool:
    return (
        len(offer.allowed_age_bands) <= 1
        or len(offer.allowed_employment_types) <= 1
        or len(offer.allowed_credit_history_bands) <= 1
        or offer.max_amount - offer.min_amount < 100_000
        or offer.max_term_months - offer.min_term_months <= 6
    )


def _recommendation(flags: list[str], offer: BankOffer) -> QualityRecommendation:
    if "missing_disclosure" in flags or "missing_advertiser_name" in flags:
        return "missing_disclosure"
    if "eligibility_too_broad" in flags or "eligibility_too_narrow" in flags:
        return "review_rules"
    if "impressions_without_clicks" in flags or "high_ctr_low_approval" in flags:
        return "pause_candidate"
    if "low_ctr" in flags:
        return "review_copy"
    if offer.partner_id == "demo" or "placeholder_affiliate_url" in flags:
        return "needs_real_partner_data"
    if "missing_affiliate_template_key" in flags or "affiliate_template_env_missing" in flags:
        return "needs_real_partner_data"
    return "keep"


def build_offer_quality_report(session: Session, *, days: int) -> OfferQualityReport:
    offers = list(session.scalars(select(BankOffer).order_by(BankOffer.id)))
    analytics = CommercialAnalyticsService(session).summary(days=days)
    metrics = {item.offer_id: item for item in analytics.offer_metrics}
    now = datetime.now(UTC).replace(tzinfo=None)
    items: list[OfferQualityItem] = []
    for offer in offers:
        metric = metrics[offer.id]
        flags: list[str] = []
        if not offer.ad_label_text.strip() or not offer.legal_disclaimer.strip():
            flags.append("missing_disclosure")
        if not offer.advertiser_name.strip():
            flags.append("missing_advertiser_name")
        if offer.partner_id != "demo" and not offer.affiliate_url_template_key:
            flags.append("missing_affiliate_template_key")
        if offer.affiliate_url_template_key and not os.getenv(offer.affiliate_url_template_key):
            flags.append("affiliate_template_env_missing")
        lowered_url = offer.affiliate_url_template.lower()
        if "example.invalid" in lowered_url or "placeholder" in lowered_url:
            flags.append("placeholder_affiliate_url")
        if offer.expires_at is not None and offer.expires_at < now:
            flags.append("expired_config")
        if metric.impressions == 0:
            flags.append("zero_impressions")
        if metric.impressions > 0 and metric.clicks == 0:
            flags.append("impressions_without_clicks")
        if metric.impressions >= 10 and metric.ctr < 0.02:
            flags.append("low_ctr")
        if (
            metric.impressions >= 10
            and metric.ctr >= 0.15
            and metric.postback_clicks >= 3
            and metric.approval_rate < 0.1
        ):
            flags.append("high_ctr_low_approval")
        if _rules_are_broad(offer):
            flags.append("eligibility_too_broad")
        if _rules_are_narrow(offer):
            flags.append("eligibility_too_narrow")
        status = "inactive"
        if offer.is_active:
            status = "expired" if "expired_config" in flags else "active"
        items.append(
            OfferQualityItem(
                offer_id=offer.id,
                product_name=offer.product_name,
                bank_id=offer.bank_id,
                status=status,
                quality_flags=flags,
                impressions=metric.impressions,
                clicks=metric.clicks,
                ctr=metric.ctr,
                postback_approval_rate=metric.approval_rate,
                postback_issued_rate=metric.issued_rate,
                estimated_revenue=metric.estimated_revenue,
                expected_revenue_proxy=metric.expected_revenue_proxy,
                recommendation=_recommendation(flags, offer),
            )
        )
    return OfferQualityReport(
        summary=OfferQualitySummary(
            active_offers=sum(1 for offer in offers if offer.is_active),
            inactive_offers=sum(1 for offer in offers if not offer.is_active),
            zero_impression_offers=sum(
                1 for item in items if "zero_impressions" in item.quality_flags
            ),
            impressions_without_clicks=sum(
                1 for item in items if "impressions_without_clicks" in item.quality_flags
            ),
        ),
        offers=items,
        warnings=[
            "Quality thresholds are operator heuristics, not automatic bank or legal decisions.",
            "Demo-only offers require real partner data before commercial activation.",
        ],
        time_window=analytics.time_window,
    )
