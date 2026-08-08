from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import CreditProfileEvent, OfferClick, OfferImpression, PartnerPostback
from src.offers.analytics import utcnow_naive
from src.offers.operator_schemas import (
    AnalyticsTimeWindow,
    SegmentOpportunity,
    SegmentOpportunityResponse,
    SegmentRecommendation,
)

SEGMENT_FIELDS = (
    "income_band",
    "risk_band",
    "pti_band",
    "employment_type",
    "credit_history_band",
    "requested_amount_band",
)


def _recommend(segment_key: str, segment_value: str, eligible_rate: float) -> SegmentRecommendation:
    if eligible_rate >= 0.8:
        return "no_action"
    if segment_key == "requested_amount_band" and segment_value == "lt_100k":
        return "add_low_amount_offer"
    if segment_key == "employment_type" and segment_value in {
        "self_employed",
        "individual_entrepreneur",
    }:
        return "add_self_employed_offer"
    if segment_key == "credit_history_band" and segment_value in {
        "minor_overdues",
        "serious_overdues",
    }:
        return "add_bad_credit_history_offer"
    if segment_key == "pti_band" and segment_value in {"high", "very_high"}:
        return "add_refinance_offer"
    if segment_key == "risk_band" and segment_value in {"high", "very_high"}:
        return "tighten_disclaimers"
    return "no_action"


def analyze_segment_opportunities(
    session: Session,
    *,
    days: int,
) -> SegmentOpportunityResponse:
    end = utcnow_naive()
    start = end - timedelta(days=days)
    profiles = list(
        session.scalars(
            select(CreditProfileEvent).where(CreditProfileEvent.created_at >= start)
        )
    )
    impressions = list(
        session.scalars(select(OfferImpression).where(OfferImpression.shown_at >= start))
    )
    clicks = list(
        session.scalars(select(OfferClick).where(OfferClick.clicked_at >= start))
    )
    postbacks = list(
        session.scalars(
            select(PartnerPostback).where(PartnerPostback.received_at >= start)
        )
    )
    profiles_with_impressions = {item.profile_id for item in impressions}
    profiles_with_clicks = {item.profile_id for item in clicks}
    profile_by_click = {item.click_id: item.profile_id for item in clicks}
    postback_profiles = {
        profile_by_click[item.click_id]
        for item in postbacks
        if item.click_id in profile_by_click
    }
    approved_profiles = {
        profile_by_click[item.click_id]
        for item in postbacks
        if item.click_id in profile_by_click and item.status in {"approved", "issued"}
    }
    groups: dict[tuple[str, str], list[CreditProfileEvent]] = defaultdict(list)
    for profile in profiles:
        for field in SEGMENT_FIELDS:
            groups[(field, str(getattr(profile, field)))].append(profile)

    opportunities: list[SegmentOpportunity] = []
    for (segment_key, segment_value), members in groups.items():
        member_ids = {item.profile_id for item in members}
        requests = len(members)
        eligible_profiles = len(member_ids & profiles_with_impressions)
        clicked_profiles = len(member_ids & profiles_with_clicks)
        known_postback_profiles = len(member_ids & postback_profiles)
        approved = len(member_ids & approved_profiles)
        eligible_rate = eligible_profiles / requests if requests else 0.0
        lost_requests = requests - eligible_profiles
        observed_click_rate = clicked_profiles / requests if requests else 0.0
        baseline_intent = max(observed_click_rate, 0.1)
        approval_rate = (
            approved / known_postback_profiles if known_postback_profiles else None
        )
        recommendation = _recommend(segment_key, segment_value, eligible_rate)
        if (
            approval_rate is not None
            and observed_click_rate >= 0.2
            and approval_rate < 0.1
        ):
            recommendation = "tighten_disclaimers"
        opportunities.append(
            SegmentOpportunity(
                segment_key=segment_key,
                segment_value=segment_value,
                requests=requests,
                eligible_offer_rate=round(eligible_rate, 6),
                click_rate=round(observed_click_rate, 6),
                approval_rate=(round(approval_rate, 6) if approval_rate is not None else None),
                estimated_lost_clicks=round(lost_requests * baseline_intent, 2),
                recommendation=recommendation,
            )
        )
    opportunities.sort(
        key=lambda item: (
            -item.estimated_lost_clicks,
            -item.requests,
            item.segment_key,
            item.segment_value,
        )
    )
    return SegmentOpportunityResponse(
        opportunities=opportunities,
        warnings=[
            "Segment metrics use band-only attributes and contain no raw profile payloads.",
            "Lost clicks are a conservative product-opportunity proxy, not forecast revenue.",
        ],
        time_window=AnalyticsTimeWindow(days=days, start=start, end=end),
    )
