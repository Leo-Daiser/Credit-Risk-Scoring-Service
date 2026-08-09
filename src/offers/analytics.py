from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import (
    BankOffer,
    CommercialFunnelEvent,
    CreditProfileEvent,
    OfferClick,
    OfferImpression,
    PartnerPostback,
)
from src.offers.operator_schemas import (
    AnalyticsTimeWindow,
    CommercialAnalyticsResponse,
    CommercialSummaryMetrics,
    EventDebugItem,
    EventDebugResponse,
    ExperimentAnalyticsMetric,
    OfferAnalyticsMetric,
    SegmentAnalyticsMetric,
)
from src.offers.revenue import build_revenue_estimates

FUNNEL_EVENT_TYPES = {
    "landing_viewed",
    "assessment_started",
    "assessment_step_completed",
    "assessment_completed",
    "calculator_used",
    "calculator_continue_clicked",
    "profile_started",
    "profile_completed",
    "profile_submitted",
    "profile_scored",
    "profile_result_viewed",
    "improvement_viewed",
    "scenario_changed",
    "scenario_started",
    "scenario_applied",
    "offers_viewed",
    "recommended_offer_viewed",
    "offer_clicked",
    "partner_transition_viewed",
    "offers_requested",
    "offers_shown",
    "result_viewed",
    "offer_card_viewed",
    "no_eligible_offers",
    "no_eligible_offers_viewed",
    "partner_redirect_failed",
}


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 6) if denominator else 0.0


def record_funnel_event(
    session: Session,
    event_type: str,
    *,
    anonymous_session_id: int | None = None,
    profile_id: str | None = None,
    offer_id: int | None = None,
    click_id: str | None = None,
    risk_band: str | None = None,
    pti_band: str | None = None,
    experiment_variant: str = "rules_v1",
    event_value: str | None = None,
) -> CommercialFunnelEvent:
    if event_type not in FUNNEL_EVENT_TYPES and event_type != "partner_postback_received":
        raise ValueError(f"Unsupported commercial funnel event: {event_type}")
    event = CommercialFunnelEvent(
        event_type=event_type,
        anonymous_session_id=anonymous_session_id,
        profile_id=profile_id,
        offer_id=offer_id,
        click_id=click_id,
        risk_band=risk_band,
        pti_band=pti_band,
        experiment_variant=experiment_variant,
        event_value=event_value,
    )
    session.add(event)
    session.flush()
    return event


class CommercialAnalyticsService:
    def __init__(self, session: Session):
        self.session = session

    def summary(
        self,
        *,
        days: int,
        offer_id: int | None = None,
        risk_band: str | None = None,
        pti_band: str | None = None,
    ) -> CommercialAnalyticsResponse:
        end = utcnow_naive()
        start = end - timedelta(days=days)
        profiles = list(
            self.session.scalars(
                select(CreditProfileEvent).where(CreditProfileEvent.created_at >= start)
            )
        )
        if risk_band:
            profiles = [profile for profile in profiles if profile.risk_band == risk_band]
        if pti_band:
            profiles = [profile for profile in profiles if profile.pti_band == pti_band]
        profile_map = {profile.profile_id: profile for profile in profiles}
        allowed_profile_ids = set(profile_map)

        events = list(
            self.session.scalars(
                select(CommercialFunnelEvent).where(
                    CommercialFunnelEvent.created_at >= start
                )
            )
        )
        if risk_band:
            events = [event for event in events if event.risk_band == risk_band]
        if pti_band:
            events = [event for event in events if event.pti_band == pti_band]

        impression_statement = select(OfferImpression).where(
            OfferImpression.shown_at >= start
        )
        click_statement = select(OfferClick).where(OfferClick.clicked_at >= start)
        postback_statement = select(PartnerPostback).where(
            PartnerPostback.received_at >= start
        )
        if offer_id is not None:
            impression_statement = impression_statement.where(
                OfferImpression.offer_id == offer_id
            )
            click_statement = click_statement.where(OfferClick.offer_id == offer_id)
            postback_statement = postback_statement.where(
                PartnerPostback.offer_id == offer_id
            )
        impressions = list(self.session.scalars(impression_statement))
        clicks = list(self.session.scalars(click_statement))
        postbacks = list(self.session.scalars(postback_statement))
        if risk_band or pti_band:
            impressions = [
                item for item in impressions if item.profile_id in allowed_profile_ids
            ]
            clicks = [item for item in clicks if item.profile_id in allowed_profile_ids]
            click_ids = {item.click_id for item in clicks}
            postbacks = [item for item in postbacks if item.click_id in click_ids]

        offers = list(self.session.scalars(select(BankOffer).order_by(BankOffer.id)))
        if offer_id is not None:
            offers = [offer for offer in offers if offer.id == offer_id]
        offer_map = {offer.id: offer for offer in offers}
        revenue_estimates = build_revenue_estimates(self.session, offers, days=days)

        impression_counts: dict[int, int] = defaultdict(int)
        click_counts: dict[int, int] = defaultdict(int)
        postback_clicks: dict[int, set[str]] = defaultdict(set)
        approvals: dict[int, set[str]] = defaultdict(set)
        issued: dict[int, set[str]] = defaultdict(set)
        revenue_by_click: dict[tuple[int, str], float] = {}
        for impression in impressions:
            impression_counts[impression.offer_id] += 1
        for click in clicks:
            click_counts[click.offer_id] += 1
        for postback in postbacks:
            postback_clicks[postback.offer_id].add(postback.click_id)
            if postback.status in {"approved", "issued"}:
                approvals[postback.offer_id].add(postback.click_id)
            if postback.status == "issued":
                issued[postback.offer_id].add(postback.click_id)
            if postback.commission_amount is not None:
                key = (postback.offer_id, postback.click_id)
                revenue_by_click[key] = max(
                    revenue_by_click.get(key, 0.0), float(postback.commission_amount)
                )

        offer_metrics: list[OfferAnalyticsMetric] = []
        for current_offer_id, offer in offer_map.items():
            impression_count = impression_counts[current_offer_id]
            click_count = click_counts[current_offer_id]
            postback_count = len(postback_clicks[current_offer_id])
            estimate = revenue_estimates[current_offer_id]
            offer_metrics.append(
                OfferAnalyticsMetric(
                    offer_id=current_offer_id,
                    product_name=offer.product_name,
                    impressions=impression_count,
                    clicks=click_count,
                    ctr=safe_rate(click_count, impression_count),
                    postback_clicks=postback_count,
                    approvals=len(approvals[current_offer_id]),
                    issued=len(issued[current_offer_id]),
                    approval_rate=safe_rate(
                        len(approvals[current_offer_id]), postback_count
                    ),
                    issued_rate=safe_rate(len(issued[current_offer_id]), postback_count),
                    estimated_revenue=round(
                        sum(
                            value
                            for (revenue_offer_id, _), value in revenue_by_click.items()
                            if revenue_offer_id == current_offer_id
                        ),
                        2,
                    ),
                    epc_proxy=(
                        round(
                            sum(
                                value
                                for (revenue_offer_id, _), value in revenue_by_click.items()
                                if revenue_offer_id == current_offer_id
                            )
                            / click_count,
                            2,
                        )
                        if click_count
                        else 0.0
                    ),
                    expected_revenue_proxy=estimate.expected_revenue_proxy,
                    revenue_estimate_source=estimate.source,
                    revenue_estimate_confidence=estimate.confidence,
                )
            )

        impressions_by_profile: dict[str, list[OfferImpression]] = defaultdict(list)
        clicks_by_profile: dict[str, list[OfferClick]] = defaultdict(list)
        for impression in impressions:
            impressions_by_profile[impression.profile_id].append(impression)
        for click in clicks:
            clicks_by_profile[click.profile_id].append(click)
        revenue_by_profile: dict[str, float] = defaultdict(float)
        click_profile = {click.click_id: click.profile_id for click in clicks}
        for (_, click_id), value in revenue_by_click.items():
            profile_id_for_click = click_profile.get(click_id)
            if profile_id_for_click:
                revenue_by_profile[profile_id_for_click] += value

        segment_groups: dict[tuple[str, str], list[CreditProfileEvent]] = defaultdict(list)
        for profile in profiles:
            segment_groups[(profile.risk_band, profile.pti_band)].append(profile)
        segment_metrics: list[SegmentAnalyticsMetric] = []
        for (segment_risk, segment_pti), segment_profiles in segment_groups.items():
            ids = {profile.profile_id for profile in segment_profiles}
            segment_impressions = sum(len(impressions_by_profile[item]) for item in ids)
            segment_clicks = sum(len(clicks_by_profile[item]) for item in ids)
            no_eligible = sum(1 for item in ids if not impressions_by_profile[item])
            segment_metrics.append(
                SegmentAnalyticsMetric(
                    risk_band=segment_risk,
                    pti_band=segment_pti,
                    requests=len(segment_profiles),
                    impressions=segment_impressions,
                    clicks=segment_clicks,
                    ctr=safe_rate(segment_clicks, segment_impressions),
                    no_eligible_requests=no_eligible,
                    revenue=round(sum(revenue_by_profile[item] for item in ids), 2),
                )
            )
        segment_metrics.sort(
            key=lambda item: (-item.requests, item.risk_band, item.pti_band)
        )

        variant_impressions: dict[str, int] = defaultdict(int)
        variant_clicks: dict[str, int] = defaultdict(int)
        variant_approved: dict[str, set[str]] = defaultdict(set)
        variant_issued: dict[str, set[str]] = defaultdict(set)
        click_variant = {click.click_id: click.experiment_variant for click in clicks}
        for impression in impressions:
            variant_impressions[impression.experiment_variant] += 1
        for click in clicks:
            variant_clicks[click.experiment_variant] += 1
        for postback in postbacks:
            variant = click_variant.get(postback.click_id, "rules_v1")
            if postback.status in {"approved", "issued"}:
                variant_approved[variant].add(postback.click_id)
            if postback.status == "issued":
                variant_issued[variant].add(postback.click_id)
        variants = sorted(set(variant_impressions) | set(variant_clicks))
        experiment_metrics = [
            ExperimentAnalyticsMetric(
                variant=variant,
                impressions=variant_impressions[variant],
                clicks=variant_clicks[variant],
                ctr=safe_rate(variant_clicks[variant], variant_impressions[variant]),
                approvals=len(variant_approved[variant]),
                issued=len(variant_issued[variant]),
            )
            for variant in variants
        ]

        event_counts: dict[str, int] = defaultdict(int)
        for event in events:
            event_counts[event.event_type] += 1
        total_profile_scores = event_counts["profile_scored"] or len(profiles)
        total_match_requests = event_counts["offers_requested"] or len(profiles)
        no_eligible_count = event_counts["no_eligible_offers"]
        if not no_eligible_count and profiles:
            no_eligible_count = sum(
                1 for profile in profiles if not impressions_by_profile[profile.profile_id]
            )
        total_postback_clicks = len({item.click_id for item in postbacks})
        total_approvals = len(
            {item.click_id for item in postbacks if item.status in {"approved", "issued"}}
        )
        total_issued = len(
            {item.click_id for item in postbacks if item.status == "issued"}
        )
        top_impressions = [item for item in impressions if item.rank == 1]
        top_pairs = {(item.profile_id, item.offer_id) for item in top_impressions}
        top_clicks = sum(
            1 for item in clicks if (item.profile_id, item.offer_id) in top_pairs
        )
        top_by_clicks = sorted(
            offer_metrics, key=lambda item: (-item.clicks, item.offer_id)
        )
        top_by_issued = sorted(
            offer_metrics, key=lambda item: (-item.issued, item.offer_id)
        )
        high_demand = [
            f"risk_band={item.risk_band};pti_band={item.pti_band}"
            for item in segment_metrics
            if item.no_eligible_requests > 0
        ][:10]
        warnings = [
            "Revenue is recorded only from validated postbacks; proxies are not guaranteed income."
        ]
        if any(offer.partner_id == "demo" for offer in offers):
            warnings.append("Demo partner estimates are synthetic and low-confidence.")
        if not postbacks:
            warnings.append("No validated postbacks exist in the selected window.")
        ctr_by_risk_band: dict[str, float] = {}
        ctr_by_pti_band: dict[str, float] = {}
        revenue_by_risk_band: dict[str, float] = defaultdict(float)
        for band in sorted({profile.risk_band for profile in profiles}):
            ids = {
                profile.profile_id for profile in profiles if profile.risk_band == band
            }
            band_impressions = sum(len(impressions_by_profile[item]) for item in ids)
            band_clicks = sum(len(clicks_by_profile[item]) for item in ids)
            ctr_by_risk_band[band] = safe_rate(band_clicks, band_impressions)
            revenue_by_risk_band[band] = round(
                sum(revenue_by_profile[item] for item in ids), 2
            )
        for band in sorted({profile.pti_band for profile in profiles}):
            ids = {profile.profile_id for profile in profiles if profile.pti_band == band}
            band_impressions = sum(len(impressions_by_profile[item]) for item in ids)
            band_clicks = sum(len(clicks_by_profile[item]) for item in ids)
            ctr_by_pti_band[band] = safe_rate(band_clicks, band_impressions)
        summary = CommercialSummaryMetrics(
            total_profile_scores=total_profile_scores,
            total_match_requests=total_match_requests,
            total_offer_impressions=len(impressions),
            total_offer_clicks=len(clicks),
            ctr_overall=safe_rate(len(clicks), len(impressions)),
            no_eligible_offers_rate=safe_rate(no_eligible_count, total_match_requests),
            postback_conversion_rate=safe_rate(total_postback_clicks, len(clicks)),
            approval_rate=safe_rate(total_approvals, total_postback_clicks),
            issued_rate=safe_rate(total_issued, total_postback_clicks),
            estimated_revenue=round(sum(revenue_by_click.values()), 2),
            epc_proxy=(
                round(sum(revenue_by_click.values()) / len(clicks), 2) if clicks else 0.0
            ),
            recommended_offer_ctr=safe_rate(top_clicks, len(top_impressions)),
            top_card_ctr=safe_rate(top_clicks, len(top_impressions)),
            partner_redirect_failures=event_counts["partner_redirect_failed"],
            assessment_start_rate=safe_rate(
                event_counts["assessment_started"], event_counts["landing_viewed"]
            ),
            assessment_completion_rate=safe_rate(
                event_counts["assessment_completed"], event_counts["assessment_started"]
            ),
            scenario_usage_rate=safe_rate(
                event_counts["scenario_applied"], event_counts["profile_result_viewed"]
            ),
            ctr_by_offer={str(item.offer_id): item.ctr for item in offer_metrics},
            ctr_by_risk_band=ctr_by_risk_band,
            ctr_by_pti_band=ctr_by_pti_band,
            revenue_by_offer={
                str(item.offer_id): item.estimated_revenue for item in offer_metrics
            },
            revenue_by_risk_band=dict(revenue_by_risk_band),
            top_offers_by_clicks=[item.offer_id for item in top_by_clicks if item.clicks][:5],
            top_offers_by_issued=[item.offer_id for item in top_by_issued if item.issued][:5],
            stale_offer_ids=[
                item.offer_id
                for item in offer_metrics
                if item.impressions > 0 and item.clicks == 0
            ],
            high_demand_no_offer_segments=high_demand,
            public_event_counts={
                event_type: event_counts[event_type]
                for event_type in sorted(FUNNEL_EVENT_TYPES)
                if event_counts[event_type]
            },
        )
        return CommercialAnalyticsResponse(
            summary=summary,
            offer_metrics=offer_metrics,
            segment_metrics=segment_metrics,
            experiment_metrics=experiment_metrics,
            warnings=warnings,
            time_window=AnalyticsTimeWindow(days=days, start=start, end=end),
        )


def recent_event_debug(session: Session, *, limit: int = 50) -> EventDebugResponse:
    clicks = list(
        session.scalars(select(OfferClick).order_by(OfferClick.clicked_at.desc()).limit(limit))
    )
    postbacks = list(
        session.scalars(
            select(PartnerPostback).order_by(PartnerPostback.received_at.desc()).limit(limit)
        )
    )
    invalid_attempts = list(
        session.scalars(
            select(CommercialFunnelEvent)
            .where(CommercialFunnelEvent.event_type == "partner_postback_received")
            .order_by(CommercialFunnelEvent.created_at.desc())
            .limit(limit)
        )
    )
    public_events = list(
        session.scalars(
            select(CommercialFunnelEvent)
            .where(CommercialFunnelEvent.event_type.in_(FUNNEL_EVENT_TYPES))
            .order_by(CommercialFunnelEvent.created_at.desc())
            .limit(limit)
        )
    )
    click_variant = {click.click_id: click.experiment_variant for click in clicks}
    events = [
        EventDebugItem(
            event_type="offer_clicked",
            click_id=click.click_id,
            offer_id=click.offer_id,
            status=None,
            hmac_validation_status=None,
            experiment_variant=click.experiment_variant,
            occurred_at=click.clicked_at,
        )
        for click in clicks
    ]
    events.extend(
        EventDebugItem(
            event_type="partner_postback_received",
            click_id=postback.click_id,
            offer_id=postback.offer_id,
            status=postback.status,
            hmac_validation_status=postback.validation_status,
            experiment_variant=click_variant.get(postback.click_id, "rules_v1"),
            occurred_at=postback.received_at,
        )
        for postback in postbacks
    )
    events.extend(
        EventDebugItem(
            event_type=event.event_type,
            click_id=event.click_id,
            offer_id=event.offer_id,
            status=None,
            hmac_validation_status=None,
            experiment_variant=event.experiment_variant,
            occurred_at=event.created_at,
        )
        for event in public_events
    )
    events.extend(
        EventDebugItem(
            event_type="partner_postback_received",
            click_id=attempt.click_id,
            offer_id=attempt.offer_id,
            status=None,
            hmac_validation_status=attempt.event_value,
            experiment_variant=attempt.experiment_variant,
            occurred_at=attempt.created_at,
        )
        for attempt in invalid_attempts
        if attempt.event_value != "valid"
    )
    events.sort(key=lambda item: item.occurred_at, reverse=True)
    return EventDebugResponse(events=events[:limit])
