from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from src.core.config import settings
from src.db.models import BankOffer
from src.offers.experiments import strategy_multipliers
from src.offers.repository import load_offer_config
from src.offers.revenue import RevenueEstimate, conservative_revenue_estimate
from src.offers.schemas import CreditProfileResult, OfferEligibilityResult, RankedOffer

PTI_SCORE = {"low": 1.0, "moderate": 0.8, "high": 0.55, "very_high": 0.2, "unknown": 0.45}
RISK_SCORE = {"low": 1.0, "medium": 0.82, "high": 0.55, "very_high": 0.25, "unknown": 0.5}
logger = logging.getLogger(__name__)
FIT_COMPONENTS = (
    "fit_score",
    "affordability_score",
    "risk_compatibility_score",
    "product_match_score",
)


def _component_scores(
    profile: CreditProfileResult,
    offer: BankOffer,
    eligibility: OfferEligibilityResult,
    revenue: RevenueEstimate,
    *,
    commercial_fit_floor: float,
) -> dict[str, float]:
    purpose_match = profile.profile_bands.loan_purpose.value == offer.product_type
    components = {
        "fit_score": 0.9 if eligibility.soft_warnings else 1.0,
        "affordability_score": PTI_SCORE[profile.pti_band.value],
        "risk_compatibility_score": RISK_SCORE.get(profile.risk_band, 0.5),
        "product_match_score": 1.0 if purpose_match else 0.65,
        "commercial_score": min(max(offer.priority / 100.0, 0.0), 1.0),
        "expected_revenue_proxy": revenue.expected_revenue_proxy,
    }
    fit_quality = min(
        components["fit_score"],
        components["affordability_score"],
        components["risk_compatibility_score"],
        components["product_match_score"],
    )
    if fit_quality < commercial_fit_floor:
        components["commercial_score"] = min(components["commercial_score"], 0.25)
        components["expected_revenue_proxy"] = min(
            components["expected_revenue_proxy"], 0.02
        )
    return components


def _ml_feature_row(
    profile: CreditProfileResult,
    offer: BankOffer,
    *,
    rule_score: float,
    rank_shown: int,
) -> dict[str, object]:
    bands = profile.profile_bands
    return {
        "offer_id": offer.id,
        "age_band": bands.age_band.value,
        "region": bands.region or "unknown",
        "income_band": bands.income_band.value,
        "employment_type": bands.employment_type.value,
        "credit_history_band": bands.credit_history_band.value,
        "requested_amount_band": bands.requested_amount_band.value,
        "term_months": bands.term_months,
        "loan_purpose": bands.loan_purpose.value,
        "risk_band": profile.risk_band,
        "pti_band": profile.pti_band.value,
        "affordability_band": profile.affordability_band.value,
        "data_coverage": profile.data_coverage,
        "product_type": offer.product_type,
        "bank_id": offer.bank_id,
        "offer_priority": offer.priority,
        "rank_shown": rank_shown,
        "rule_score": rule_score,
    }


def rank_offers(
    profile: CreditProfileResult,
    eligible_offers: Iterable[tuple[BankOffer, OfferEligibilityResult]],
    context: dict[str, Any] | None = None,
    *,
    config: dict[str, Any] | None = None,
    revenue_estimates: dict[int, RevenueEstimate] | None = None,
    experiment_variant: str = "rules_v1",
) -> list[RankedOffer]:
    del context
    ranking_config = (config or load_offer_config())["ranking"]
    base_weights = {key: float(value) for key, value in ranking_config["weights"].items()}
    fit_multiplier, revenue_multiplier = strategy_multipliers(experiment_variant)
    effective_weights = dict(base_weights)
    for key in FIT_COMPONENTS:
        effective_weights[key] *= fit_multiplier
    effective_weights["expected_revenue_proxy"] *= revenue_multiplier
    total_weight = sum(effective_weights.values())
    weights = {key: value / total_weight for key, value in effective_weights.items()}
    penalty = ranking_config["confidence_penalties"][profile.confidence_level.value]
    commercial_fit_floor = float(ranking_config.get("commercial_fit_floor", 0.55))
    tiebreaker_tolerance = float(
        ranking_config.get("commercial_tiebreaker_tolerance", 0.03)
    )
    scored: list[tuple[float, int, int, BankOffer, OfferEligibilityResult, dict[str, float]]] = []
    for offer, eligibility in eligible_offers:
        if not eligibility.eligible:
            continue
        revenue = (revenue_estimates or {}).get(
            offer.id, conservative_revenue_estimate(offer)
        )
        components = _component_scores(
            profile,
            offer,
            eligibility,
            revenue,
            commercial_fit_floor=commercial_fit_floor,
        )
        weighted = {name: round(components[name] * float(weight), 8) for name, weight in weights.items()}
        final_score = round(sum(weighted.values()) * float(penalty), 8)
        fit_weight = sum(effective_weights[name] for name in FIT_COMPONENTS)
        fit_quality_score = sum(
            components[name] * effective_weights[name] for name in FIT_COMPONENTS
        ) / fit_weight
        commercial_tiebreaker_score = (
            weighted["commercial_score"] + weighted["expected_revenue_proxy"]
        )
        breakdown = {
            **components,
            **{f"weighted_{name}": value for name, value in weighted.items()},
            "confidence_penalty": float(penalty),
            "pre_penalty_score": round(sum(weighted.values()), 8),
            "final_score": final_score,
            "fit_quality_score": round(fit_quality_score, 8),
            "commercial_tiebreaker_score": round(commercial_tiebreaker_score, 8),
            "commercial_tiebreaker_used": 0.0,
        }
        scored.append((final_score, offer.priority, offer.id, offer, eligibility, breakdown))
    scored.sort(key=lambda item: (-item[5]["fit_quality_score"], item[2]))
    fit_first: list[
        tuple[float, int, int, BankOffer, OfferEligibilityResult, dict[str, float]]
    ] = []
    while scored:
        leader = scored.pop(0)
        leader_fit = leader[5]["fit_quality_score"]
        group = [leader]
        if leader_fit >= commercial_fit_floor:
            while (
                scored
                and scored[0][5]["fit_quality_score"] >= commercial_fit_floor
                and leader_fit - scored[0][5]["fit_quality_score"] <= tiebreaker_tolerance
            ):
                group.append(scored.pop(0))
        if len(group) > 1:
            commercial_values = {
                item[5]["commercial_tiebreaker_score"] for item in group
            }
            if len(commercial_values) > 1:
                for item in group:
                    item[5]["commercial_tiebreaker_used"] = 1.0
                logger.info(
                    "offer_ranking_commercial_tiebreaker_used",
                    extra={"offer_ids": [item[2] for item in group]},
                )
            group.sort(
                key=lambda item: (
                    -item[5]["commercial_tiebreaker_score"],
                    -item[5]["fit_quality_score"],
                    -item[1],
                    item[2],
                )
            )
        fit_first.extend(group)
    scored = fit_first
    ml_fallback = False
    if settings.offer_ranker_mode == "ml" and scored:
        try:
            artifact = joblib.load(Path(settings.offer_ranker_model_path))
            rows = [
                _ml_feature_row(profile, item[3], rule_score=item[0], rank_shown=index)
                for index, item in enumerate(scored, start=1)
            ]
            feature_columns = artifact["feature_columns"]
            frame = pd.DataFrame(rows).reindex(columns=feature_columns)
            probabilities = artifact["pipeline"].predict_proba(frame)[:, 1]
            scored = [
                (
                    round(float(probability), 8),
                    item[1],
                    item[2],
                    item[3],
                    item[4],
                    {**item[5], "rules_final_score": item[0], "ml_score": float(probability)},
                )
                for item, probability in zip(scored, probabilities, strict=True)
            ]
            scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        except (
            AttributeError,
            EOFError,
            FileNotFoundError,
            ImportError,
            KeyError,
            OSError,
            TypeError,
            ValueError,
        ):
            ml_fallback = True
    ranked: list[RankedOffer] = []
    for rank, (score, _, _, offer, eligibility, breakdown) in enumerate(scored, start=1):
        ranked.append(
            RankedOffer(
                offer_id=offer.id,
                rank=rank,
                bank_id=offer.bank_id,
                product_name=offer.product_name,
                advertiser_name=offer.advertiser_name,
                final_score=score,
                score_breakdown=breakdown,
                match_reasons=eligibility.reasons,
                warnings=eligibility.soft_warnings
                + (["ML ranker unavailable; rules fallback used"] if ml_fallback else []),
                ad_disclosure=offer.ad_label_text,
                redirect_url=f"/v1/offers/{offer.id}/click",
                revenue_estimate_source=(revenue_estimates or {})
                .get(offer.id, conservative_revenue_estimate(offer))
                .source,
                revenue_estimate_confidence=(revenue_estimates or {})
                .get(offer.id, conservative_revenue_estimate(offer))
                .confidence,
                experiment_variant=experiment_variant,
            )
        )
    return ranked
