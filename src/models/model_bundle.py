"""Serializable production model bundle and inference helpers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

BUNDLE_FORMAT_VERSION = 1
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_ARTIFACT_INPUTS = {
    "baseline_metrics_sha256",
    "baseline_model_sha256",
    "dependency_lock_sha256",
    "feature_schema_sha256",
    "packaging_code_sha256",
    "production_config_sha256",
    "source_metrics_sha256",
    "source_model_sha256",
    "training_data_sha256",
}


def derive_model_version(model_type: str, artifact_inputs: dict[str, str]) -> str:
    """Derive the runtime model identity from a canonical artifact manifest."""
    payload = json.dumps(
        artifact_inputs,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:12]
    return f"{model_type}-{digest}"


@dataclass
class ModelBundle:
    """Self-contained model artifact used by online and batch inference."""

    model: Any
    metadata: dict[str, Any]
    feature_schema: dict[str, Any]
    reference_stats: dict[str, Any]

    def validate_contract(self) -> None:
        """Reject incomplete or incompatible production artifacts.

        Joblib only restores Python objects; it does not prove that the object
        follows the runtime contract expected by the API and batch jobs. This
        validation runs before a deserialized bundle is accepted for serving.
        """
        if not isinstance(self.metadata, dict):
            raise ValueError("Model bundle metadata must be a dictionary.")
        if not isinstance(self.feature_schema, dict):
            raise ValueError("Model bundle feature_schema must be a dictionary.")
        if not isinstance(self.reference_stats, dict):
            raise ValueError("Model bundle reference_stats must be a dictionary.")

        format_version = self.metadata.get("bundle_format_version")
        if format_version != BUNDLE_FORMAT_VERSION:
            raise ValueError(
                "Unsupported model bundle format: "
                f"{format_version!r}; expected {BUNDLE_FORMAT_VERSION}. "
                "Regenerate the production bundle with the current code."
            )

        required_metadata = {
            "model_version",
            "model_type",
            "feature_count",
            "decision_threshold",
            "risk_bands",
            "artifact_inputs",
            "input_contract",
        }
        missing_metadata = sorted(required_metadata - set(self.metadata))
        if missing_metadata:
            raise ValueError(f"Model bundle metadata is missing: {missing_metadata}.")
        if not str(self.metadata["model_version"]).strip():
            raise ValueError("Model bundle model_version must be non-empty.")
        if not str(self.metadata["model_type"]).strip():
            raise ValueError("Model bundle model_type must be non-empty.")
        if not callable(getattr(self.model, "predict_proba", None)):
            raise ValueError("Model bundle estimator must implement predict_proba().")

        feature_names = self.feature_schema.get("feature_names")
        numeric_features = self.feature_schema.get("numeric_features")
        categorical_features = self.feature_schema.get("categorical_features")
        for name, values in (
            ("feature_names", feature_names),
            ("numeric_features", numeric_features),
            ("categorical_features", categorical_features),
        ):
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise ValueError(f"Model bundle {name} must be a list of non-empty strings.")
        if not feature_names:
            raise ValueError("Model bundle feature_names must not be empty.")
        if len(feature_names) != len(set(feature_names)):
            raise ValueError("Model bundle feature_names must be unique.")
        numeric_set = set(numeric_features)
        categorical_set = set(categorical_features)
        if numeric_set & categorical_set:
            raise ValueError("Numeric and categorical feature sets must be disjoint.")
        if numeric_set | categorical_set != set(feature_names):
            raise ValueError(
                "Numeric and categorical features must form the complete feature schema."
            )
        if int(self.metadata["feature_count"]) != len(feature_names):
            raise ValueError("Model bundle feature_count does not match feature_schema.")

        input_contract = self.metadata["input_contract"]
        if not isinstance(input_contract, dict):
            raise ValueError("Model bundle input_contract must be a dictionary.")
        required_features = input_contract.get("required_features")
        if not isinstance(required_features, list) or any(
            not isinstance(value, str) or not value for value in required_features
        ):
            raise ValueError("Model bundle required_features must be a list of strings.")
        if len(required_features) != len(set(required_features)):
            raise ValueError("Model bundle required_features must be unique.")
        unknown_required = sorted(set(required_features) - set(feature_names))
        if unknown_required:
            raise ValueError(
                f"Model bundle required_features contains unknown features: {unknown_required}."
            )
        minimum_coverage = float(input_contract.get("min_feature_coverage", -1.0))
        if not np.isfinite(minimum_coverage) or not 0.0 <= minimum_coverage <= 1.0:
            raise ValueError("Model bundle min_feature_coverage must be within [0, 1].")

        threshold = float(self.metadata["decision_threshold"])
        if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise ValueError("Model bundle decision_threshold must be within [0, 1].")
        self._validate_risk_bands(self.metadata["risk_bands"])

        artifact_inputs = self.metadata["artifact_inputs"]
        if not isinstance(artifact_inputs, dict):
            raise ValueError("Model bundle artifact_inputs must be a dictionary.")
        missing_inputs = sorted(REQUIRED_ARTIFACT_INPUTS - set(artifact_inputs))
        if missing_inputs:
            raise ValueError(f"Model bundle artifact_inputs is missing: {missing_inputs}.")
        invalid_hashes = sorted(
            name
            for name in REQUIRED_ARTIFACT_INPUTS
            if not isinstance(artifact_inputs[name], str)
            or SHA256_PATTERN.fullmatch(artifact_inputs[name]) is None
        )
        if invalid_hashes:
            raise ValueError(
                f"Model bundle artifact_inputs contains invalid SHA-256 values: {invalid_hashes}."
            )
        expected_version = derive_model_version(str(self.metadata["model_type"]), artifact_inputs)
        if self.metadata["model_version"] != expected_version:
            raise ValueError(
                "Model bundle model_version does not match its artifact_inputs manifest: "
                f"{self.metadata['model_version']!r} != {expected_version!r}."
            )

        numeric_reference = self.reference_stats.get("numeric")
        categorical_reference = self.reference_stats.get("categorical")
        if not isinstance(numeric_reference, dict) or not isinstance(
            categorical_reference, dict
        ):
            raise ValueError("Model bundle reference_stats requires numeric and categorical maps.")
        if not set(numeric_reference).issubset(numeric_set):
            raise ValueError("Numeric reference statistics contain unknown features.")
        if not set(categorical_reference).issubset(categorical_set):
            raise ValueError("Categorical reference statistics contain unknown features.")

    @staticmethod
    def _validate_risk_bands(risk_bands: Any) -> None:
        if not isinstance(risk_bands, list) or not risk_bands:
            raise ValueError("Model bundle risk_bands must be a non-empty list.")
        previous = 0.0
        for index, band in enumerate(risk_bands):
            if not isinstance(band, dict) or not str(band.get("name", "")).strip():
                raise ValueError("Every model bundle risk band must have a name.")
            upper = band.get("upper_bound")
            if upper is None:
                if index != len(risk_bands) - 1:
                    raise ValueError("Only the last model bundle risk band may be open-ended.")
                continue
            upper_value = float(upper)
            if not np.isfinite(upper_value) or not previous < upper_value <= 1.0:
                raise ValueError("Model bundle risk band bounds must increase within (0, 1].")
            previous = upper_value
        if risk_bands[-1].get("upper_bound") is not None:
            raise ValueError("Model bundle risk_bands must end with an open-ended band.")

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
