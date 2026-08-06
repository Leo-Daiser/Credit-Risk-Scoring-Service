"""Calibrate a trained classifier and package it for production inference."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split

try:
    from sklearn.frozen import FrozenEstimator
except ImportError:  # scikit-learn < 1.6 compatibility
    FrozenEstimator = None

from src.models.model_bundle import ModelBundle
from src.models.train_baseline import (
    DEFAULT_THRESHOLD_GRID,
    evaluate_binary_classifier,
    load_training_data,
    save_json,
    select_best_threshold,
    split_features_target,
)


def load_production_config(config_path: str | Path) -> dict[str, Any]:
    """Load and validate the ``production_model`` config section."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Train config not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    section = config.get("production_model") if isinstance(config, dict) else None
    if not isinstance(section, dict):
        raise ValueError("Train config must contain a 'production_model' section.")

    required = (
        "source_model_path",
        "source_metrics_path",
        "feature_schema_path",
        "train_features_path",
        "bundle_output_path",
        "metadata_output_path",
    )
    missing = [key for key in required if key not in section]
    if missing:
        raise ValueError(f"Production model config is missing keys: {missing}.")
    return section


def validate_source_training_contract(
    config: dict[str, Any],
    source_metrics: dict[str, Any],
    feature_schema: dict[str, Any],
) -> dict[str, Any]:
    """Prove that the frozen source model used the holdout excluded below."""
    required = {"model_type", "random_seed", "validation_size", "feature_count"}
    missing = sorted(required - set(source_metrics))
    if missing:
        raise ValueError(f"Source model metrics are missing split contract keys: {missing}.")

    expected_seed = int(config.get("random_seed", 42))
    source_seed = int(source_metrics["random_seed"])
    if source_seed != expected_seed:
        raise ValueError(
            "Source model random_seed does not match production_model.random_seed: "
            f"{source_seed} != {expected_seed}."
        )

    expected_holdout = float(config.get("holdout_size", 0.2))
    source_holdout = float(source_metrics["validation_size"])
    if not np.isclose(source_holdout, expected_holdout, rtol=0.0, atol=1e-12):
        raise ValueError(
            "Source model validation_size does not match production_model.holdout_size: "
            f"{source_holdout} != {expected_holdout}."
        )

    expected_features = len(feature_schema["feature_names"])
    source_features = int(source_metrics["feature_count"])
    if source_features != expected_features:
        raise ValueError(
            "Source model feature_count does not match the feature schema: "
            f"{source_features} != {expected_features}."
        )

    return {
        "model_type": str(source_metrics["model_type"]),
        "random_seed": source_seed,
        "validation_size": source_holdout,
        "feature_count": source_features,
    }


def expected_calibration_error(
    y_true: Any,
    y_probability: Any,
    n_bins: int = 10,
) -> float:
    """Compute equal-width expected calibration error (ECE)."""
    if n_bins < 2:
        raise ValueError("n_bins must be at least 2.")
    y = np.asarray(y_true, dtype="float64")
    probabilities = np.asarray(y_probability, dtype="float64")
    if len(y) != len(probabilities) or len(y) == 0:
        raise ValueError("y_true and y_probability must have equal non-zero length.")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_ids = np.minimum(np.digitize(probabilities, edges[1:-1]), n_bins - 1)
    error = 0.0
    for bin_id in range(n_bins):
        mask = bin_ids == bin_id
        if not mask.any():
            continue
        error += float(mask.mean()) * abs(
            float(probabilities[mask].mean()) - float(y[mask].mean())
        )
    return float(error)


def build_reference_stats(
    frame: pd.DataFrame,
    numeric_features: list[str],
    categorical_features: list[str],
) -> dict[str, Any]:
    """Build compact training-distribution statistics for drift monitoring."""
    numeric: dict[str, Any] = {}
    for column in numeric_features:
        values = pd.to_numeric(frame[column], errors="coerce")
        non_null = values.dropna()
        quantiles = non_null.quantile([0.1, 0.25, 0.5, 0.75, 0.9]) if len(non_null) else None
        distribution_edges: list[float] = []
        distribution_proportions: list[float] = []
        if quantiles is not None:
            distribution_edges = sorted({float(value) for value in quantiles})
            histogram_edges = [-np.inf, *distribution_edges, np.inf]
            counts, _ = np.histogram(non_null.to_numpy(dtype="float64"), bins=histogram_edges)
            distribution_proportions = (counts / max(int(counts.sum()), 1)).tolist()
        numeric[column] = {
            "mean": None if not len(non_null) else float(non_null.mean()),
            "std": None if not len(non_null) else float(non_null.std(ddof=0)),
            "missing_rate": float(values.isna().mean()),
            "quantiles": [] if quantiles is None else [float(value) for value in quantiles],
            "distribution_edges": distribution_edges,
            "distribution_proportions": [float(value) for value in distribution_proportions],
        }

    categorical: dict[str, Any] = {}
    for column in categorical_features:
        values = frame[column].fillna("__MISSING__").astype(str)
        frequencies = values.value_counts(normalize=True, dropna=False).head(20)
        categorical[column] = {
            "missing_rate": float(frame[column].isna().mean()),
            "top_frequencies": {str(key): float(value) for key, value in frequencies.items()},
            "other_rate": float(max(0.0, 1.0 - frequencies.sum())),
        }
    return {"numeric": numeric, "categorical": categorical}


def _validate_risk_bands(risk_bands: Any) -> list[dict[str, Any]]:
    if not isinstance(risk_bands, list) or not risk_bands:
        raise ValueError("risk_bands must be a non-empty list.")
    previous = 0.0
    result: list[dict[str, Any]] = []
    for index, band in enumerate(risk_bands):
        if not isinstance(band, dict) or not band.get("name"):
            raise ValueError("Each risk band must contain a name.")
        upper = band.get("upper_bound")
        if upper is None:
            if index != len(risk_bands) - 1:
                raise ValueError("Only the last risk band may omit upper_bound.")
        else:
            upper = float(upper)
            if not previous < upper <= 1.0:
                raise ValueError("Risk band upper bounds must increase within (0, 1].")
            previous = upper
        result.append({"name": str(band["name"]), "upper_bound": upper})
    if result[-1]["upper_bound"] is not None:
        result.append({"name": "very_high", "upper_bound": None})
    return result


def _artifact_version(
    path: Path,
    model_type: str,
    config: dict[str, Any],
    feature_schema: dict[str, Any],
) -> str:
    """Hash every inference-relevant input into the model version."""
    digest_builder = hashlib.sha256(path.read_bytes())
    version_config = {
        key: config.get(key)
        for key in (
            "calibration_method",
            "calibration_cv",
            "holdout_size",
            "calibration_fraction",
            "random_seed",
            "selected_threshold_metric",
            "thresholds",
            "risk_bands",
        )
    }
    digest_builder.update(
        json.dumps(version_config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest_builder.update(
        json.dumps(feature_schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest = digest_builder.hexdigest()[:12]
    return f"{model_type}-{digest}"


def prepare_production_model(
    config_path: str | Path = "configs/train.yaml",
) -> dict[str, Any]:
    """Calibrate the baseline on one split and evaluate on an untouched split."""
    config = load_production_config(config_path)
    source_model_path = Path(config["source_model_path"])
    source_metrics_path = Path(config["source_metrics_path"])
    schema_path = Path(config["feature_schema_path"])
    if not source_model_path.exists():
        raise FileNotFoundError(f"Source model not found: {source_model_path}")
    if not source_metrics_path.exists():
        raise FileNotFoundError(f"Source model metrics not found: {source_metrics_path}")
    if not schema_path.exists():
        raise FileNotFoundError(f"Feature schema not found: {schema_path}")

    with schema_path.open("r", encoding="utf-8") as file:
        feature_schema = json.load(file)
    with source_metrics_path.open("r", encoding="utf-8") as file:
        source_metrics = json.load(file)
    if not isinstance(source_metrics, dict):
        raise ValueError("Source model metrics must be a JSON object.")
    source_model = joblib.load(source_model_path)
    frame = load_training_data(config["train_features_path"])
    X, y, feature_names = split_features_target(
        frame,
        id_column=feature_schema["id_column"],
        target_column=feature_schema["target_column"],
    )
    if feature_names != feature_schema["feature_names"]:
        raise ValueError("Training data columns do not match the feature schema.")

    source_training = validate_source_training_contract(
        config,
        source_metrics,
        feature_schema,
    )

    random_seed = int(config.get("random_seed", 42))
    holdout_size = float(config.get("holdout_size", 0.2))
    calibration_fraction = float(config.get("calibration_fraction", 0.5))
    if not 0.0 < holdout_size < 1.0 or not 0.0 < calibration_fraction < 1.0:
        raise ValueError("holdout_size and calibration_fraction must be in (0, 1).")

    X_source_train, X_holdout, _, y_holdout = train_test_split(
        X,
        y,
        test_size=holdout_size,
        random_state=random_seed,
        stratify=y,
    )
    X_calibration, X_evaluation, y_calibration, y_evaluation = train_test_split(
        X_holdout,
        y_holdout,
        train_size=calibration_fraction,
        random_state=random_seed,
        stratify=y_holdout,
    )

    method = str(config.get("calibration_method", "sigmoid"))
    if FrozenEstimator is not None:
        calibrated_model = CalibratedClassifierCV(
            FrozenEstimator(source_model),
            method=method,
            cv=int(config.get("calibration_cv", 5)),
        )
    else:  # pragma: no cover - exercised only by older developer environments
        calibrated_model = CalibratedClassifierCV(source_model, method=method, cv="prefit")
    calibrated_model.fit(X_calibration, y_calibration)

    calibration_probability = calibrated_model.predict_proba(X_calibration)[:, 1]
    raw_probability = source_model.predict_proba(X_evaluation)[:, 1]
    calibrated_probability = calibrated_model.predict_proba(X_evaluation)[:, 1]

    thresholds = [
        float(value) for value in config.get("thresholds", DEFAULT_THRESHOLD_GRID)
    ]
    calibration_metrics = evaluate_binary_classifier(
        y_calibration, calibration_probability, thresholds=thresholds
    )
    selection = select_best_threshold(
        calibration_metrics["threshold_metrics"],
        metric_name=str(config.get("selected_threshold_metric", "f1")),
    )
    threshold = float(selection["best_threshold"])
    raw_metrics = evaluate_binary_classifier(
        y_evaluation, raw_probability, threshold=threshold, thresholds=thresholds
    )
    calibrated_metrics = evaluate_binary_classifier(
        y_evaluation,
        calibrated_probability,
        threshold=threshold,
        thresholds=thresholds,
    )
    raw_metrics["expected_calibration_error"] = expected_calibration_error(
        y_evaluation, raw_probability
    )
    calibrated_metrics["expected_calibration_error"] = expected_calibration_error(
        y_evaluation, calibrated_probability
    )

    risk_bands = _validate_risk_bands(
        config.get(
            "risk_bands",
            [
                {"name": "low", "upper_bound": 0.05},
                {"name": "medium", "upper_bound": 0.10},
                {"name": "high", "upper_bound": 0.20},
                {"name": "very_high", "upper_bound": None},
            ],
        )
    )
    model_type = str(config.get("model_type", "logistic_regression_calibrated"))
    model_version = str(
        config.get("model_version")
        or _artifact_version(source_model_path, model_type, config, feature_schema)
    )
    reference_stats = build_reference_stats(
        X_source_train,
        feature_schema["numeric_features"],
        feature_schema["categorical_features"],
    )
    metadata = {
        "model_version": model_version,
        "model_type": model_type,
        "created_at": datetime.now(UTC).isoformat(),
        "calibration_method": method,
        "decision_threshold": threshold,
        "threshold_metric": selection["metric_name"],
        "risk_bands": risk_bands,
        "feature_count": len(feature_names),
        "training_rows": int(len(X_source_train)),
        "calibration_rows": int(len(X_calibration)),
        "evaluation_rows": int(len(X_evaluation)),
        "source_model_sha256": hashlib.sha256(source_model_path.read_bytes()).hexdigest(),
        "source_training": source_training,
        "metrics": {
            "raw": raw_metrics,
            "calibrated": calibrated_metrics,
        },
    }
    bundle = ModelBundle(
        model=calibrated_model,
        metadata=metadata,
        feature_schema=feature_schema,
        reference_stats=reference_stats,
    )

    bundle_path = Path(config["bundle_output_path"])
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, bundle_path)
    save_json(metadata, config["metadata_output_path"])

    return {
        "model_version": model_version,
        "model_type": model_type,
        "decision_threshold": threshold,
        "training_rows": int(len(X_source_train)),
        "calibration_rows": int(len(X_calibration)),
        "evaluation_rows": int(len(X_evaluation)),
        "raw_brier_score": raw_metrics["brier_score"],
        "calibrated_brier_score": calibrated_metrics["brier_score"],
        "raw_ece": raw_metrics["expected_calibration_error"],
        "calibrated_ece": calibrated_metrics["expected_calibration_error"],
        "bundle_output_path": str(bundle_path),
        "metadata_output_path": str(config["metadata_output_path"]),
    }
