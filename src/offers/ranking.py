from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from src.core.config import settings
from src.db.models import BankOffer
from src.offers.repository import load_offer_config
from src.offers.schemas import CreditProfileResult, OfferEligibilityResult, RankedOffer

PTI_SCORE = {"low": 1.0, "moderate": 0.8, "high": 0.55, "very_high": 0.2, "unknown": 0.45}
RISK_SCORE = {"low": 1.0, "medium": 0.82, "high": 0.55, "very_high": 0.25, "unknown": 0.5}


def _component_scores(profile: CreditProfileResult, offer: BankOffer) -> dict[str, float]:
    purpose_match = profile.profile_bands.loan_purpose.value == offer.product_type
    return {
        "user_fit_score": 1.0,
        "affordability_fit_score": PTI_SCORE[profile.pti_band.value],
        "risk_compatibility_score": RISK_SCORE.get(profile.risk_band, 0.5),
        "product_match_score": 1.0 if purpose_match else 0.65,
        "commercial_score": min(max(offer.priority / 100.0, 0.0), 1.0),
    }


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
) -> list[RankedOffer]:
    del context
    ranking_config = (config or load_offer_config())["ranking"]
    weights = ranking_config["weights"]
    penalty = ranking_config["confidence_penalties"][profile.confidence_level.value]
    scored: list[tuple[float, int, int, BankOffer, OfferEligibilityResult, dict[str, float]]] = []
    for offer, eligibility in eligible_offers:
        if not eligibility.eligible:
            continue
        components = _component_scores(profile, offer)
        weighted = {name: round(components[name] * float(weight), 8) for name, weight in weights.items()}
        final_score = round(sum(weighted.values()) * float(penalty), 8)
        breakdown = {
            **components,
            **{f"weighted_{name}": value for name, value in weighted.items()},
            "confidence_penalty": float(penalty),
            "pre_penalty_score": round(sum(weighted.values()), 8),
            "final_score": final_score,
        }
        scored.append((final_score, offer.priority, offer.id, offer, eligibility, breakdown))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
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
            )
        )
    return ranked
