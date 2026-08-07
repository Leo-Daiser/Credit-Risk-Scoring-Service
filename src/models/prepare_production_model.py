"""Calibrate a trained classifier and package it for production inference."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
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

from src.models.evaluation import (
    bootstrap_metric_intervals,
    bootstrap_roc_auc_difference,
    build_subgroup_report,
    evaluate_acceptance_gates,
    select_cost_sensitive_threshold,
)
from src.models.model_bundle import BUNDLE_FORMAT_VERSION, ModelBundle, derive_model_version
from src.models.train_baseline import (
    DEFAULT_THRESHOLD_GRID,
    evaluate_binary_classifier,
    load_training_data,
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
        "baseline_model_path",
        "baseline_metrics_path",
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
        error += float(mask.mean()) * abs(float(probabilities[mask].mean()) - float(y[mask].mean()))
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
            "min": None if not len(non_null) else float(non_null.min()),
            "max": None if not len(non_null) else float(non_null.max()),
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
            "allowed_values": sorted(str(value) for value in values.unique()),
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


def _validate_input_contract(
    input_contract: Any,
    feature_names: list[str],
) -> dict[str, Any]:
    if not isinstance(input_contract, dict):
        raise ValueError("production_model.input_contract must be a dictionary.")
    required_features = input_contract.get("required_features")
    if not isinstance(required_features, list) or any(
        not isinstance(value, str) or not value for value in required_features
    ):
        raise ValueError("input_contract.required_features must be a list of strings.")
    if len(required_features) != len(set(required_features)):
        raise ValueError("input_contract.required_features must be unique.")
    unknown = sorted(set(required_features) - set(feature_names))
    if unknown:
        raise ValueError(f"Required input features are absent from the schema: {unknown}.")
    minimum_coverage = float(input_contract.get("min_feature_coverage", -1.0))
    if not np.isfinite(minimum_coverage) or not 0.0 <= minimum_coverage <= 1.0:
        raise ValueError("input_contract.min_feature_coverage must be within [0, 1].")
    return {
        "required_features": list(required_features),
        "min_feature_coverage": minimum_coverage,
    }


VERSION_CONFIG_KEYS = (
    "acceptance_gates",
    "bootstrap_samples",
    "calibration_cv",
    "calibration_fraction",
    "calibration_method",
    "confidence_level",
    "holdout_size",
    "input_contract",
    "random_seed",
    "risk_bands",
    "subgroup_min_rows",
    "threshold_policy",
    "thresholds",
)
PACKAGING_CODE_PATHS = (
    "src/models/evaluation.py",
    "src/models/model_bundle.py",
    "src/models/prepare_production_model.py",
    "src/models/train_baseline.py",
)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a potentially large artifact without loading it into memory."""
    artifact_path = Path(path)
    digest = hashlib.sha256()
    with artifact_path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    """Hash a JSON-compatible value using a canonical representation."""
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_artifact_input_fingerprints(
    config: dict[str, Any],
    feature_schema: dict[str, Any],
) -> dict[str, str]:
    """Fingerprint every input that can change bundle content or acceptance."""
    version_config = {key: config.get(key) for key in VERSION_CONFIG_KEYS}
    project_root = Path(__file__).resolve().parents[2]
    packaging_code = {
        relative_path: sha256_file(project_root / relative_path)
        for relative_path in PACKAGING_CODE_PATHS
    }
    return {
        "source_model_sha256": sha256_file(config["source_model_path"]),
        "source_metrics_sha256": sha256_file(config["source_metrics_path"]),
        "baseline_model_sha256": sha256_file(config["baseline_model_path"]),
        "baseline_metrics_sha256": sha256_file(config["baseline_metrics_path"]),
        "training_data_sha256": sha256_file(config["train_features_path"]),
        "feature_schema_sha256": sha256_json(feature_schema),
        "production_config_sha256": sha256_json(version_config),
        "packaging_code_sha256": sha256_json(packaging_code),
        "dependency_lock_sha256": sha256_file(project_root / "requirements.txt"),
    }


def artifact_version(model_type: str, artifact_inputs: dict[str, str]) -> str:
    """Derive one stable version from all bundle-producing inputs."""
    return derive_model_version(model_type, artifact_inputs)


def _temporary_output_path(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def save_production_artifacts_atomically(
    bundle: ModelBundle,
    metadata: dict[str, Any],
    bundle_path: str | Path,
    metadata_path: str | Path,
) -> None:
    """Replace validated runtime artifacts only after both writes succeed."""
    resolved_bundle_path = Path(bundle_path)
    resolved_metadata_path = Path(metadata_path)
    if resolved_bundle_path == resolved_metadata_path:
        raise ValueError("Bundle and metadata output paths must be different.")
    bundle.validate_contract()

    temporary_bundle = _temporary_output_path(resolved_bundle_path)
    temporary_metadata = _temporary_output_path(resolved_metadata_path)
    try:
        joblib.dump(bundle, temporary_bundle)
        with temporary_metadata.open("w", encoding="utf-8") as file:
            json.dump(metadata, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())

        # The bundle is the serving source of truth, so publish it last.
        os.replace(temporary_metadata, resolved_metadata_path)
        os.replace(temporary_bundle, resolved_bundle_path)
    finally:
        temporary_bundle.unlink(missing_ok=True)
        temporary_metadata.unlink(missing_ok=True)


def prepare_production_model(
    config_path: str | Path = "configs/train.yaml",
) -> dict[str, Any]:
    """Calibrate the baseline on one split and evaluate on an untouched split."""
    config = load_production_config(config_path)
    source_model_path = Path(config["source_model_path"])
    source_metrics_path = Path(config["source_metrics_path"])
    baseline_model_path = Path(config["baseline_model_path"])
    baseline_metrics_path = Path(config["baseline_metrics_path"])
    schema_path = Path(config["feature_schema_path"])
    training_data_path = Path(config["train_features_path"])
    if not source_model_path.exists():
        raise FileNotFoundError(f"Source model not found: {source_model_path}")
    if not source_metrics_path.exists():
        raise FileNotFoundError(f"Source model metrics not found: {source_metrics_path}")
    if not baseline_model_path.exists():
        raise FileNotFoundError(f"Baseline model not found: {baseline_model_path}")
    if not baseline_metrics_path.exists():
        raise FileNotFoundError(f"Baseline metrics not found: {baseline_metrics_path}")
    if not schema_path.exists():
        raise FileNotFoundError(f"Feature schema not found: {schema_path}")
    if not training_data_path.exists():
        raise FileNotFoundError(f"Training data not found: {training_data_path}")

    with schema_path.open("r", encoding="utf-8") as file:
        feature_schema = json.load(file)
    with source_metrics_path.open("r", encoding="utf-8") as file:
        source_metrics = json.load(file)
    with baseline_metrics_path.open("r", encoding="utf-8") as file:
        baseline_metrics = json.load(file)
    if not isinstance(source_metrics, dict):
        raise ValueError("Source model metrics must be a JSON object.")
    if not isinstance(baseline_metrics, dict):
        raise ValueError("Baseline metrics must be a JSON object.")
    artifact_inputs = build_artifact_input_fingerprints(config, feature_schema)
    source_model = joblib.load(source_model_path)
    baseline_model = joblib.load(baseline_model_path)
    frame = load_training_data(config["train_features_path"])
    X, y, feature_names = split_features_target(
        frame,
        id_column=feature_schema["id_column"],
        target_column=feature_schema["target_column"],
    )
    if feature_names != feature_schema["feature_names"]:
        raise ValueError("Training data columns do not match the feature schema.")
    input_contract = _validate_input_contract(config.get("input_contract"), feature_names)

    source_training = validate_source_training_contract(
        config,
        source_metrics,
        feature_schema,
    )
    baseline_training = validate_source_training_contract(
        config,
        baseline_metrics,
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
    baseline_probability = baseline_model.predict_proba(X_evaluation)[:, 1]

    thresholds = [float(value) for value in config.get("thresholds", DEFAULT_THRESHOLD_GRID)]
    calibration_metrics = evaluate_binary_classifier(
        y_calibration, calibration_probability, thresholds=thresholds
    )
    threshold_policy = config.get("threshold_policy") or {}
    if not isinstance(threshold_policy, dict):
        raise ValueError("production_model.threshold_policy must be a dictionary.")
    strategy = str(threshold_policy.get("strategy", "expected_cost"))
    if strategy == "expected_cost":
        selection = select_cost_sensitive_threshold(
            calibration_metrics["threshold_metrics"],
            false_negative_cost=float(threshold_policy.get("false_negative_cost", 5.0)),
            false_positive_cost=float(threshold_policy.get("false_positive_cost", 1.0)),
            min_recall=float(threshold_policy.get("min_recall", 0.0)),
            max_predicted_positive_rate=float(
                threshold_policy.get("max_predicted_positive_rate", 1.0)
            ),
        )
    elif strategy == "metric":
        selection = select_best_threshold(
            calibration_metrics["threshold_metrics"],
            metric_name=str(threshold_policy.get("metric_name", "f1")),
        )
    else:
        raise ValueError(f"Unsupported threshold policy strategy: {strategy}.")
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
    baseline_evaluation_metrics = evaluate_binary_classifier(
        y_evaluation,
        baseline_probability,
        threshold=threshold,
        thresholds=thresholds,
    )
    confidence_intervals = bootstrap_metric_intervals(
        y_evaluation,
        calibrated_probability,
        n_bootstrap=int(config.get("bootstrap_samples", 200)),
        confidence_level=float(config.get("confidence_level", 0.95)),
        random_seed=random_seed,
    )
    baseline_comparison_interval = bootstrap_roc_auc_difference(
        y_evaluation,
        calibrated_probability,
        baseline_probability,
        n_bootstrap=int(config.get("bootstrap_samples", 200)),
        confidence_level=float(config.get("confidence_level", 0.95)),
        random_seed=random_seed,
    )
    subgroup_report = build_subgroup_report(
        X_evaluation,
        y_evaluation,
        calibrated_probability,
        threshold=threshold,
        min_rows=int(config.get("subgroup_min_rows", 500)),
    )
    baseline_roc_auc = float(baseline_evaluation_metrics["roc_auc"])
    acceptance_config = config.get("acceptance_gates") or {}
    if not isinstance(acceptance_config, dict):
        raise ValueError("production_model.acceptance_gates must be a dictionary.")
    acceptance_report = evaluate_acceptance_gates(
        calibrated_metrics,
        raw_metrics,
        confidence_intervals,
        acceptance_config,
        baseline_roc_auc=baseline_roc_auc,
        baseline_comparison_interval=baseline_comparison_interval,
    )
    if acceptance_report["status"] != "passed":
        failed = [check["name"] for check in acceptance_report["checks"] if not check["passed"]]
        raise RuntimeError(f"Production model failed acceptance gates: {failed}.")

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
    model_version = artifact_version(model_type, artifact_inputs)
    configured_model_version = config.get("model_version")
    if configured_model_version is not None and str(configured_model_version) != model_version:
        raise ValueError(
            "Configured model_version does not match the deterministic artifact version: "
            f"{configured_model_version!r} != {model_version!r}."
        )
    reference_stats = build_reference_stats(
        X_source_train,
        feature_schema["numeric_features"],
        feature_schema["categorical_features"],
    )
    metadata = {
        "bundle_format_version": BUNDLE_FORMAT_VERSION,
        "model_version": model_version,
        "model_type": model_type,
        "created_at": datetime.now(UTC).isoformat(),
        "calibration_method": method,
        "decision_threshold": threshold,
        "input_contract": input_contract,
        "threshold_policy": selection,
        "risk_bands": risk_bands,
        "feature_count": len(feature_names),
        "training_rows": int(len(X_source_train)),
        "calibration_rows": int(len(X_calibration)),
        "evaluation_rows": int(len(X_evaluation)),
        "artifact_inputs": artifact_inputs,
        "source_model_sha256": artifact_inputs["source_model_sha256"],
        "source_training": source_training,
        "baseline_comparison": {
            "training_contract": baseline_training,
            "model_sha256": artifact_inputs["baseline_model_sha256"],
            "evaluation_metrics": baseline_evaluation_metrics,
            "roc_auc_difference_interval": baseline_comparison_interval,
        },
        "confidence_intervals": confidence_intervals,
        "subgroup_monitoring": subgroup_report,
        "acceptance": acceptance_report,
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
    save_production_artifacts_atomically(
        bundle,
        metadata,
        bundle_path,
        config["metadata_output_path"],
    )

    return {
        "model_version": model_version,
        "model_type": model_type,
        "decision_threshold": threshold,
        "acceptance_status": acceptance_report["status"],
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
