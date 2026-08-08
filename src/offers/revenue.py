from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import BankOffer, OfferClick, OfferImpression, PartnerPostback

DEFAULT_CLICK_PRIOR = 0.04
DEFAULT_APPROVAL_PRIOR = 0.08
DEFAULT_ISSUE_PRIOR = 0.35
COMMISSION_NORMALIZER = 5_000.0


@dataclass(frozen=True)
class RevenueEstimate:
    click_probability: float
    approval_probability: float
    issue_probability: float
    commission_proxy: float
    expected_revenue_proxy: float
    estimated_revenue_per_impression: float
    source: str
    confidence: str


def _cutoff(days: int) -> datetime:
    return (datetime.now(UTC) - timedelta(days=days)).replace(tzinfo=None)


def build_revenue_estimates(
    session: Session,
    offers: list[BankOffer],
    *,
    days: int = 90,
) -> dict[int, RevenueEstimate]:
    since = _cutoff(days)
    offer_ids = [offer.id for offer in offers]
    if not offer_ids:
        return {}
    impressions = list(
        session.scalars(
            select(OfferImpression).where(
                OfferImpression.offer_id.in_(offer_ids), OfferImpression.shown_at >= since
            )
        )
    )
    clicks = list(
        session.scalars(
            select(OfferClick).where(
                OfferClick.offer_id.in_(offer_ids), OfferClick.clicked_at >= since
            )
        )
    )
    postbacks = list(
        session.scalars(
            select(PartnerPostback).where(
                PartnerPostback.offer_id.in_(offer_ids), PartnerPostback.received_at >= since
            )
        )
    )
    impression_counts: dict[int, int] = {}
    click_counts: dict[int, int] = {}
    approved_clicks: dict[int, set[str]] = {}
    issued_clicks: dict[int, set[str]] = {}
    revenue_by_click: dict[tuple[int, str], float] = {}
    for impression in impressions:
        impression_counts[impression.offer_id] = impression_counts.get(impression.offer_id, 0) + 1
    for click in clicks:
        click_counts[click.offer_id] = click_counts.get(click.offer_id, 0) + 1
    for postback in postbacks:
        if postback.status in {"approved", "issued"}:
            approved_clicks.setdefault(postback.offer_id, set()).add(postback.click_id)
        if postback.status == "issued":
            issued_clicks.setdefault(postback.offer_id, set()).add(postback.click_id)
        if postback.commission_amount is not None:
            key = (postback.offer_id, postback.click_id)
            revenue_by_click[key] = max(
                revenue_by_click.get(key, 0.0), float(postback.commission_amount)
            )

    estimates: dict[int, RevenueEstimate] = {}
    for offer in offers:
        impression_count = impression_counts.get(offer.id, 0)
        click_count = click_counts.get(offer.id, 0)
        approved_count = len(approved_clicks.get(offer.id, set()))
        issued_count = len(issued_clicks.get(offer.id, set()))
        click_probability = (click_count + 2.0) / (impression_count + 50.0)
        approval_probability = (approved_count + 1.6) / (click_count + 20.0)
        issue_probability = (issued_count + 1.75) / (approved_count + 5.0)
        historical_revenue = sum(
            value for (offer_id, _), value in revenue_by_click.items() if offer_id == offer.id
        )
        historical_commission = historical_revenue / issued_count if issued_count else 0.0
        configured_commission = float(offer.commission_amount or 0.0)
        commission_value = historical_commission or configured_commission
        if (offer.partner_id or "demo") == "demo":
            # Synthetic commission values must not bias product ranking.
            commission_value = 500.0
        commission_proxy = min(max(commission_value / COMMISSION_NORMALIZER, 0.0), 1.0)
        expected_proxy = (
            click_probability
            * approval_probability
            * issue_probability
            * commission_proxy
        )
        if impression_count >= 20 and click_count >= 3:
            source = "historical"
            confidence = "medium" if approved_count else "low"
        elif (offer.partner_id or "demo") == "demo":
            source = "demo_only"
            confidence = "low"
        else:
            source = "conservative_prior"
            confidence = "low"
        estimates[offer.id] = RevenueEstimate(
            click_probability=round(click_probability, 8),
            approval_probability=round(approval_probability, 8),
            issue_probability=round(issue_probability, 8),
            commission_proxy=round(commission_proxy, 8),
            expected_revenue_proxy=round(expected_proxy, 8),
            estimated_revenue_per_impression=round(
                click_probability
                * approval_probability
                * issue_probability
                * commission_value,
                2,
            ),
            source=source,
            confidence=confidence,
        )
    return estimates


def conservative_revenue_estimate(offer: BankOffer) -> RevenueEstimate:
    commission_value = (
        500.0
        if (offer.partner_id or "demo") == "demo"
        else float(offer.commission_amount or 0.0)
    )
    commission_proxy = min(max(commission_value / COMMISSION_NORMALIZER, 0.0), 1.0)
    expected = (
        DEFAULT_CLICK_PRIOR
        * DEFAULT_APPROVAL_PRIOR
        * DEFAULT_ISSUE_PRIOR
        * commission_proxy
    )
    return RevenueEstimate(
        click_probability=DEFAULT_CLICK_PRIOR,
        approval_probability=DEFAULT_APPROVAL_PRIOR,
        issue_probability=DEFAULT_ISSUE_PRIOR,
        commission_proxy=round(commission_proxy, 8),
        expected_revenue_proxy=round(expected, 8),
        estimated_revenue_per_impression=round(
            DEFAULT_CLICK_PRIOR
            * DEFAULT_APPROVAL_PRIOR
            * DEFAULT_ISSUE_PRIOR
            * commission_value,
            2,
        ),
        source=(
            "demo_only" if (offer.partner_id or "demo") == "demo" else "conservative_prior"
        ),
        confidence="low",
    )
