"""Serializable production model bundle and inference helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ModelBundle:
    """Self-contained model artifact used by online and batch inference."""

    model: Any
    metadata: dict[str, Any]
    feature_schema: dict[str, Any]
    reference_stats: dict[str, Any]

    @property
    def feature_names(self) -> list[str]:
        return list(self.feature_schema["feature_names"])

    def prepare_frame(self, records: list[dict[str, Any]]) -> pd.DataFrame:
        """Validate feature names and align records to the training schema."""
        if not records:
            raise ValueError("At least one feature record is required.")

        expected = set(self.feature_names)
        unknown = sorted({key for row in records for key in row} - expected)
        if unknown:
            sample = unknown[:10]
            suffix = "" if len(unknown) <= 10 else f" (+{len(unknown) - 10} more)"
            raise ValueError(f"Unknown model features: {sample}{suffix}.")

        frame = pd.DataFrame(records).reindex(columns=self.feature_names)

        invalid_numeric: list[str] = []
        for column in self.feature_schema.get("numeric_features", []):
            original = frame[column]
            converted = pd.to_numeric(original, errors="coerce")
            invalid = original.notna() & (converted.isna() | ~np.isfinite(converted))
            if invalid.any():
                invalid_numeric.append(column)
            frame[column] = converted
        if invalid_numeric:
            sample = invalid_numeric[:10]
            suffix = "" if len(invalid_numeric) <= 10 else f" (+{len(invalid_numeric) - 10} more)"
            raise ValueError(
                f"Numeric model features must contain finite numbers or null: {sample}{suffix}."
            )
        for column in self.feature_schema.get("categorical_features", []):
            frame[column] = frame[column].astype("object")
        return frame

    def predict_default_probability(self, frame: pd.DataFrame) -> np.ndarray:
        """Return positive-class probabilities for an aligned feature frame."""
        probabilities = np.asarray(self.model.predict_proba(frame), dtype="float64")
        if probabilities.ndim != 2 or probabilities.shape[1] != 2:
            raise RuntimeError("The production model must return binary probabilities.")
        return probabilities[:, 1]

    def assess_input_quality(
        self,
        record: dict[str, Any],
        prepared_frame: pd.DataFrame,
    ) -> dict[str, Any]:
        """Describe feature completeness and training-domain deviations."""
        expected = set(self.feature_names)
        supplied = {key for key, value in record.items() if key in expected and value is not None}
        row = prepared_frame.iloc[0]
        numeric_reference = self.reference_stats.get("numeric", {})
        categorical_reference = self.reference_stats.get("categorical", {})

        out_of_range: list[str] = []
        for feature, stats in numeric_reference.items():
            value = row.get(feature)
            if pd.isna(value):
                continue
            minimum = stats.get("min")
            maximum = stats.get("max")
            if (minimum is not None and float(value) < float(minimum)) or (
                maximum is not None and float(value) > float(maximum)
            ):
                out_of_range.append(feature)

        unseen_categories: list[str] = []
        for feature, stats in categorical_reference.items():
            value = row.get(feature)
            if pd.isna(value):
                continue
            allowed = stats.get("allowed_values")
            if allowed is not None and str(value) not in set(allowed):
                unseen_categories.append(feature)

        warnings: list[str] = []
        if out_of_range:
            warnings.append("numeric_values_outside_training_range")
        if unseen_categories:
            warnings.append("categorical_values_not_seen_in_training")
        supplied_count = len(supplied)
        total = len(self.feature_names)
        return {
            "supplied_feature_count": supplied_count,
            "supplied_feature_coverage": supplied_count / total if total else 0.0,
            "missing_feature_count": int(row.isna().sum()),
            "out_of_range_features": sorted(out_of_range),
            "unseen_categorical_features": sorted(unseen_categories),
            "warnings": warnings,
        }

    def risk_band(self, probability: float) -> str:
        """Map a calibrated probability to the configured risk band."""
        bands = self.metadata.get("risk_bands", [])
        for band in bands:
            upper_bound = band.get("upper_bound")
            if upper_bound is None or probability < float(upper_bound):
                return str(band["name"])
        raise RuntimeError("Model bundle has no terminal risk band.")
