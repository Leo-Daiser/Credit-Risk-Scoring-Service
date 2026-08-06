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
                "Numeric model features must contain finite numbers or null: "
                f"{sample}{suffix}."
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

    def risk_band(self, probability: float) -> str:
        """Map a calibrated probability to the configured risk band."""
        bands = self.metadata.get("risk_bands", [])
        for band in bands:
            upper_bound = band.get("upper_bound")
            if upper_bound is None or probability < float(upper_bound):
                return str(band["name"])
        raise RuntimeError("Model bundle has no terminal risk band.")
