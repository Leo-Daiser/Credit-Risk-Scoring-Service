from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.offers.affordability import estimate_amount_from_band, estimate_income_from_band
from src.offers.schemas import AgeBand, CreditProfileInput


class ScoringProtocol(Protocol):
    def score(self, features: dict[str, object], request_id: str | None = None) -> dict[str, object]: ...


@dataclass(frozen=True)
class RiskProfileAssessment:
    risk_score_available: bool = False
    risk_score: float | None = None
    risk_band: str = "unknown"
    model_version: str | None = None
    data_coverage: float = 0.0
    warnings: list[str] = field(default_factory=list)


AGE_MIDPOINT = {
    AgeBand.AGE_18_21: 20,
    AgeBand.AGE_22_30: 26,
    AgeBand.AGE_31_45: 38,
    AgeBand.AGE_46_60: 53,
    AgeBand.AGE_60_PLUS: 65,
}


def _limited_feature_payload(profile: CreditProfileInput) -> dict[str, object]:
    amount = profile.requested_amount or estimate_amount_from_band(profile.requested_amount_band)
    income = estimate_income_from_band(profile.income_band)
    payload: dict[str, object] = {
        "DAYS_BIRTH": -365 * AGE_MIDPOINT[profile.age_band],
        "AMT_CREDIT": amount,
    }
    if income is not None:
        payload["AMT_INCOME_TOTAL"] = income
        payload["CREDIT_INCOME_RATIO"] = amount / income
    return payload


def assess_risk_profile(
    profile: CreditProfileInput,
    scoring_service: ScoringProtocol | None,
    *,
    minimum_public_coverage: float = 0.5,
) -> RiskProfileAssessment:
    if scoring_service is None:
        return RiskProfileAssessment(warnings=["Model bundle unavailable"])
    features = _limited_feature_payload(profile)
    try:
        result = scoring_service.score(features)
    except (KeyError, TypeError, ValueError) as exc:
        return RiskProfileAssessment(
            data_coverage=min(len(features) / 8.0, 1.0),
            warnings=[f"Risk score unavailable for the short profile: {type(exc).__name__}"],
        )
    quality = result.get("input_quality", {})
    coverage = (
        float(
            quality.get(
                "supplied_feature_coverage",
                quality.get("coverage", len(features) / 8.0),
            )
        )
        if isinstance(quality, dict)
        else 0.0
    )
    warnings = list(quality.get("warnings", [])) if isinstance(quality, dict) else []
    if coverage < minimum_public_coverage:
        warnings.append("Risk model feature coverage is low; score is not exposed")
        return RiskProfileAssessment(
            data_coverage=coverage,
            model_version=str(result.get("model_version") or "") or None,
            warnings=warnings,
        )
    return RiskProfileAssessment(
        risk_score_available=True,
        risk_score=float(result["default_probability"]),
        risk_band=str(result["risk_band"]),
        model_version=str(result.get("model_version") or "") or None,
        data_coverage=coverage,
        warnings=warnings,
    )
