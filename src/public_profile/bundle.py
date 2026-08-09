"""Serializable contract for the consumer-compatible Riskline model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

PUBLIC_BUNDLE_FORMAT_VERSION = 2


@dataclass
class PublicProfileModelBundle:
    """Versioned model artifact trained on the normalized public schema."""

    model: Any
    metadata: dict[str, Any]
    feature_schema: dict[str, list[str]]
    reference_stats: dict[str, Any]

    def validate_contract(self) -> None:
        if self.metadata.get("bundle_format_version") != PUBLIC_BUNDLE_FORMAT_VERSION:
            raise ValueError("Unsupported public profile bundle format")
        for field in (
            "model_name",
            "model_version",
            "training_source",
            "training_date",
            "population_limitations",
            "risk_bands",
            "acceptance_status",
        ):
            if field not in self.metadata:
                raise ValueError(f"Public profile bundle metadata is missing: {field}")
        numeric = self.feature_schema.get("numeric_features")
        categorical = self.feature_schema.get("categorical_features")
        if not isinstance(numeric, list) or not isinstance(categorical, list):
            raise ValueError("Public profile feature schema is invalid")
        feature_names = self.feature_schema.get("feature_names")
        if feature_names != numeric + categorical or not feature_names:
            raise ValueError("Public profile feature ordering is invalid")
        if not callable(getattr(self.model, "predict_proba", None)):
            raise ValueError("Public profile estimator must implement predict_proba")
        if not isinstance(self.reference_stats.get("probability_quantiles"), dict):
            raise ValueError("Public profile probability reference is missing")

    @property
    def feature_names(self) -> list[str]:
        return list(self.feature_schema["feature_names"])

    def prepare_frame(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        self.validate_contract()
        return pd.DataFrame(rows).reindex(columns=self.feature_names)
