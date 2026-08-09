"""Inference facade for the Riskline Public Profile Model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib

from src.offers.schemas import CreditProfileInput
from src.public_profile.bundle import PublicProfileModelBundle
from src.public_profile.explainability import explain_public_profile, safe_factor_payload
from src.public_profile.mapping import public_feature_row

RISKLINE_INDEX_MODEL_MIN = 20.0
RISKLINE_INDEX_MODEL_MAX = 90.0
RISKLINE_INDEX_OUTPUT_MIN = 10
RISKLINE_INDEX_OUTPUT_MAX = 95
RISKLINE_INDEX_PTI_REFERENCE = 0.35
RISKLINE_INDEX_PTI_PENALTY_PER_UNIT = 35.0


@dataclass(frozen=True)
class PublicProfileAssessment:
    model_available: bool = False
    ml_personalized: bool = False
    model_version: str | None = None
    default_probability: float | None = None
    risk_band: str = "unknown"
    riskline_index: int | None = None
    profile_band: str = "insufficient_data"
    data_coverage: float = 0.0
    strengths: list[dict[str, Any]] = field(default_factory=list)
    limiting_factors: list[dict[str, Any]] = field(default_factory=list)
    actionable_factors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_public_profile_bundle(path: str | Path) -> PublicProfileModelBundle:
    bundle_path = Path(path)
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Public profile model bundle not found: {bundle_path}")
    bundle = joblib.load(bundle_path)
    if not isinstance(bundle, PublicProfileModelBundle):
        raise TypeError("Artifact is not a PublicProfileModelBundle")
    bundle.validate_contract()
    return bundle


class PublicProfileScoringService:
    def __init__(self, bundle: PublicProfileModelBundle, artifact_path: str = "in-memory"):
        bundle.validate_contract()
        self.bundle = bundle
        self.artifact_path = artifact_path

    @classmethod
    def from_path(cls, path: str | Path) -> PublicProfileScoringService:
        return cls(load_public_profile_bundle(path), artifact_path=str(path))

    def model_info(self) -> dict[str, Any]:
        metadata = self.bundle.metadata
        return {
            "model_name": metadata["model_name"],
            "model_version": metadata["model_version"],
            "training_source": metadata["training_source"],
            "training_date": metadata["training_date"],
            "feature_count": len(self.bundle.feature_names),
            "acceptance_status": metadata["acceptance_status"],
            "metrics": metadata.get("metrics", {}),
            "population_limitations": metadata["population_limitations"],
        }

    def score(self, profile: CreditProfileInput) -> PublicProfileAssessment:
        row = public_feature_row(profile)
        frame = self.bundle.prepare_frame([row])
        probability = float(self.bundle.model.predict_proba(frame)[0, 1])
        risk_band = self._risk_band(probability)
        index = self._riskline_index(probability, float(row.get("pti", 0.0)))
        strengths, limitations = explain_public_profile(
            self.bundle,
            row,
            probability,
        )
        supplied = [
            profile.age is not None,
            profile.monthly_income is not None,
            profile.employment_years is not None,
            profile.requested_amount is not None,
            profile.existing_monthly_payments is not None,
            profile.employment_type.value != "unknown",
        ]
        coverage = round(0.55 + 0.45 * sum(supplied) / len(supplied), 4)
        limitations_payload = [safe_factor_payload(item) for item in limitations]
        return PublicProfileAssessment(
            model_available=True,
            ml_personalized=True,
            model_version=str(self.bundle.metadata["model_version"]),
            default_probability=probability,
            risk_band=risk_band,
            riskline_index=index,
            profile_band=_profile_band(index),
            data_coverage=coverage,
            strengths=[safe_factor_payload(item) for item in strengths],
            limiting_factors=limitations_payload,
            actionable_factors=[
                item for item in limitations_payload if item["actionable"]
            ],
            warnings=[
                "Оценка построена без данных БКИ и банковского андеррайтинга.",
                "Модель обучена на открытой зарубежной выборке и требует локальной перекалибровки.",
            ],
        )

    def _risk_band(self, probability: float) -> str:
        for band in self.bundle.metadata["risk_bands"]:
            upper = band.get("upper_bound")
            if upper is None or probability <= float(upper):
                return str(band["name"])
        return "very_high"

    def _riskline_index(self, probability: float, pti: float) -> int:
        quantiles = self.bundle.reference_stats["probability_quantiles"]
        low = float(quantiles["q05"])
        high = float(quantiles["q95"])
        if high <= low:
            normalized = 0.5
        else:
            normalized = 1.0 - min(max((probability - low) / (high - low), 0.0), 1.0)
        model_index = RISKLINE_INDEX_MODEL_MIN + normalized * (
            RISKLINE_INDEX_MODEL_MAX - RISKLINE_INDEX_MODEL_MIN
        )
        affordability_penalty = (
            max(pti - RISKLINE_INDEX_PTI_REFERENCE, 0.0)
            * RISKLINE_INDEX_PTI_PENALTY_PER_UNIT
        )
        return int(
            round(
                min(
                    max(
                        model_index - affordability_penalty,
                        RISKLINE_INDEX_OUTPUT_MIN,
                    ),
                    RISKLINE_INDEX_OUTPUT_MAX,
                )
            )
        )


def _profile_band(index: int) -> str:
    if index >= 70:
        return "strong"
    if index >= 50:
        return "stable"
    if index >= 30:
        return "constrained"
    return "high_attention"
