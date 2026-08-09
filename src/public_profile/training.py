"""Train and package the real Riskline Public Profile Model."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from src.models.train_baseline import build_logistic_regression_pipeline
from src.models.train_catboost import build_catboost_pipeline
from src.public_profile.bundle import (
    PUBLIC_BUNDLE_FORMAT_VERSION,
    PublicProfileModelBundle,
)
from src.public_profile.mapping import (
    PUBLIC_CATEGORICAL_FEATURES,
    PUBLIC_FEATURES,
    PUBLIC_NUMERIC_FEATURES,
    HomeCreditPublicTrainingAdapter,
)
from src.public_profile.training_schema import validate_normalized_training_frame


def load_public_model_config(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Public profile model config not found: {source}")
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Public profile model config must be a mapping")
    for section in ("source", "training", "outputs", "provenance"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"Public profile model config requires '{section}'")
    return config


def build_normalized_training_dataset(
    config_path: str | Path = "configs/public_profile_model.yaml",
) -> dict[str, Any]:
    config = load_public_model_config(config_path)
    source = Path(config["source"]["application_train_path"])
    if not source.is_file():
        raise FileNotFoundError(
            f"Public model source data not found: {source}. Keep raw data outside Git."
        )
    columns = [
        "SK_ID_CURR",
        "TARGET",
        "DAYS_BIRTH",
        "DAYS_EMPLOYED",
        "AMT_INCOME_TOTAL",
        "AMT_CREDIT",
        "AMT_ANNUITY",
        "NAME_INCOME_TYPE",
    ]
    raw = pd.read_csv(source, usecols=columns)
    max_rows = int(config["source"].get("max_rows") or 0)
    if max_rows and len(raw) > max_rows:
        raw, _ = train_test_split(
            raw,
            train_size=max_rows,
            random_state=int(config["training"]["random_seed"]),
            stratify=raw["TARGET"],
        )
    normalized = HomeCreditPublicTrainingAdapter().transform(raw)
    validate_normalized_training_frame(normalized)
    output = Path(config["source"]["normalized_output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_parquet(output, index=False)
    return {"rows": len(normalized), "output_path": str(output)}


def train_public_profile_model(
    config_path: str | Path = "configs/public_profile_model.yaml",
) -> dict[str, Any]:
    config = load_public_model_config(config_path)
    normalized_path = Path(config["source"]["normalized_output_path"])
    if not normalized_path.is_file():
        build_normalized_training_dataset(config_path)
    data = pd.read_parquet(normalized_path)
    validate_normalized_training_frame(data)
    X = data[PUBLIC_FEATURES].copy()
    y = data["target"].astype("int64")
    seed = int(config["training"]["random_seed"])
    validation_size = float(config["training"]["validation_size"])
    calibration_size = float(config["training"]["calibration_size"])
    X_train, X_holdout, y_train, y_holdout = train_test_split(
        X,
        y,
        test_size=validation_size + calibration_size,
        random_state=seed,
        stratify=y,
    )
    relative_validation = validation_size / (validation_size + calibration_size)
    X_calibration, X_validation, y_calibration, y_validation = train_test_split(
        X_holdout,
        y_holdout,
        test_size=relative_validation,
        random_state=seed,
        stratify=y_holdout,
    )

    logistic = build_logistic_regression_pipeline(
        PUBLIC_NUMERIC_FEATURES,
        PUBLIC_CATEGORICAL_FEATURES,
        **config["training"].get("logistic", {}),
    )
    logistic.fit(X_train, y_train)
    catboost = build_catboost_pipeline(
        PUBLIC_NUMERIC_FEATURES,
        PUBLIC_CATEGORICAL_FEATURES,
        random_seed=seed,
        **config["training"].get("catboost", {}),
    )
    catboost.fit(X_train, y_train)
    candidates = {"logistic_regression": logistic, "catboost": catboost}
    candidate_metrics = {
        name: _metrics(y_validation, model.predict_proba(X_validation)[:, 1])
        for name, model in candidates.items()
    }
    selected_name = max(
        candidate_metrics,
        key=lambda name: (
            candidate_metrics[name]["roc_auc"],
            -candidate_metrics[name]["brier_score"],
        ),
    )
    selected = candidates[selected_name]
    calibrated = CalibratedClassifierCV(
        FrozenEstimator(selected),
        method=str(config["training"].get("calibration_method", "sigmoid")),
    )
    calibrated.fit(X_calibration, y_calibration)
    validation_probability = calibrated.predict_proba(X_validation)[:, 1]
    calibrated_metrics = _metrics(y_validation, validation_probability)
    gates = config["training"].get("acceptance_gates", {})
    accepted = (
        calibrated_metrics["roc_auc"] >= float(gates.get("min_roc_auc", 0.6))
        and calibrated_metrics["brier_score"] <= float(gates.get("max_brier_score", 0.12))
    )
    if not accepted:
        raise RuntimeError(
            "Public profile model failed acceptance gates: "
            f"roc_auc={calibrated_metrics['roc_auc']:.4f}, "
            f"brier={calibrated_metrics['brier_score']:.4f}"
        )
    probability_quantiles = {
        name: float(value)
        for name, value in zip(
            ("q05", "q25", "q50", "q75", "q95"),
            np.quantile(validation_probability, [0.05, 0.25, 0.5, 0.75, 0.95]),
            strict=True,
        )
    }
    risk_bands = [
        {"name": "low", "upper_bound": probability_quantiles["q25"]},
        {"name": "medium", "upper_bound": probability_quantiles["q50"]},
        {"name": "high", "upper_bound": probability_quantiles["q75"]},
        {"name": "very_high", "upper_bound": None},
    ]
    training_date = datetime.now(UTC).replace(microsecond=0).isoformat()
    version_manifest = {
        "schema": PUBLIC_FEATURES,
        "rows": len(data),
        "selected_candidate": selected_name,
        "training": config["training"],
        "source": config["provenance"]["training_source"],
        "metrics": {key: round(value, 8) for key, value in calibrated_metrics.items()},
    }
    version_digest = sha256(
        json.dumps(version_manifest, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()[:12]
    version = f"riskline-public-v2-{selected_name}-{version_digest}"
    bundle = PublicProfileModelBundle(
        model=calibrated,
        metadata={
            "bundle_format_version": PUBLIC_BUNDLE_FORMAT_VERSION,
            "model_name": "Riskline Public Profile Model",
            "model_version": version,
            "selected_candidate": selected_name,
            "training_source": config["provenance"]["training_source"],
            "training_date": training_date,
            "population_limitations": config["provenance"]["population_limitations"],
            "metrics": calibrated_metrics,
            "candidate_metrics": candidate_metrics,
            "risk_bands": risk_bands,
            "acceptance_status": "accepted",
            "version_manifest": version_manifest,
        },
        feature_schema={
            "feature_names": PUBLIC_FEATURES,
            "numeric_features": PUBLIC_NUMERIC_FEATURES,
            "categorical_features": PUBLIC_CATEGORICAL_FEATURES,
        },
        reference_stats={
            "numeric_medians": {
                column: _json_scalar(X_train[column].median())
                for column in PUBLIC_NUMERIC_FEATURES
            },
            "categorical_modes": {
                column: str(X_train[column].mode(dropna=True).iloc[0])
                for column in PUBLIC_CATEGORICAL_FEATURES
            },
            "probability_quantiles": probability_quantiles,
        },
    )
    bundle.validate_contract()
    outputs = config["outputs"]
    bundle_path = Path(outputs["bundle_path"])
    metrics_path = Path(outputs["metrics_path"])
    schema_path = Path(outputs["feature_schema_path"])
    for path in (bundle_path, metrics_path, schema_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, bundle_path)
    metrics_path.write_text(
        json.dumps(bundle.metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    schema_path.write_text(
        json.dumps(bundle.feature_schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "model_version": version,
        "selected_candidate": selected_name,
        "rows": len(data),
        "metrics": calibrated_metrics,
        "candidate_metrics": candidate_metrics,
        "bundle_path": str(bundle_path),
        "acceptance_status": "accepted",
    }


def _metrics(y_true: pd.Series, probability: np.ndarray) -> dict[str, float]:
    return {
        "roc_auc": float(roc_auc_score(y_true, probability)),
        "pr_auc": float(average_precision_score(y_true, probability)),
        "brier_score": float(brier_score_loss(y_true, probability)),
    }


def _json_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value
