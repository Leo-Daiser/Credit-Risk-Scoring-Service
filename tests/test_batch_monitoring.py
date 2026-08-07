import json

import joblib
import numpy as np
import pandas as pd
import pytest
import yaml

from src.core.config import settings
from src.models.model_bundle import (
    BUNDLE_FORMAT_VERSION,
    REQUIRED_ARTIFACT_INPUTS,
    ModelBundle,
    derive_model_version,
)
from src.models.prepare_production_model import build_reference_stats
from src.models.train_baseline import build_logistic_regression_pipeline
from src.services.batch import run_batch_scoring
from src.services.monitoring import (
    build_drift_report,
    population_stability_index,
    run_drift_monitoring,
)


def _bundle_and_reference(tmp_path, input_contract=None):
    rng = np.random.default_rng(3)
    training = pd.DataFrame(
        {
            "INCOME": rng.normal(100_000, 15_000, 200),
            "AGE": rng.integers(20, 70, 200).astype(float),
            "CONTRACT": rng.choice(["cash", "revolving"], 200),
        }
    )
    target = ((training["INCOME"] < 95_000) | (training["CONTRACT"] == "cash")).astype(int)
    model = build_logistic_regression_pipeline(
        ["INCOME", "AGE"], ["CONTRACT"], solver="liblinear", n_jobs=None
    )
    model.fit(training, target)
    reference = build_reference_stats(training, ["INCOME", "AGE"], ["CONTRACT"])
    artifact_inputs = {name: "0" * 64 for name in REQUIRED_ARTIFACT_INPUTS}
    model_version = derive_model_version("logistic_regression", artifact_inputs)
    bundle = ModelBundle(
        model=model,
        metadata={
            "bundle_format_version": BUNDLE_FORMAT_VERSION,
            "model_version": model_version,
            "model_type": "logistic_regression",
            "feature_count": 3,
            "decision_threshold": 0.5,
            "input_contract": input_contract
            or {"required_features": [], "min_feature_coverage": 0.0},
            "artifact_inputs": artifact_inputs,
            "risk_bands": [
                {"name": "low", "upper_bound": 0.3},
                {"name": "high", "upper_bound": None},
            ],
        },
        feature_schema={
            "id_column": "SK_ID_CURR",
            "target_column": "TARGET",
            "feature_names": ["INCOME", "AGE", "CONTRACT"],
            "numeric_features": ["INCOME", "AGE"],
            "categorical_features": ["CONTRACT"],
        },
        reference_stats=reference,
    )
    bundle_path = tmp_path / "bundle.joblib"
    joblib.dump(bundle, bundle_path)
    return bundle_path, training, reference


def test_population_stability_index_detects_shift():
    assert population_stability_index([0.5, 0.5], [0.5, 0.5]) == 0.0
    assert population_stability_index([0.9, 0.1], [0.1, 0.9]) > 1.0


def test_batch_scoring_and_drift_monitoring_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "model_bundle_path", None)
    bundle_path, training, _ = _bundle_and_reference(tmp_path)
    batch_input = training.iloc[:12].copy()
    batch_input.insert(0, "SK_ID_CURR", np.arange(12))
    input_path = tmp_path / "input.parquet"
    scores_path = tmp_path / "scores.parquet"
    summary_path = tmp_path / "batch_summary.json"
    drift_path = tmp_path / "drift.json"
    batch_input.to_parquet(input_path, index=False)
    config = {
        "model": {"bundle_path": str(bundle_path)},
        "batch_scoring": {
            "input_path": str(input_path),
            "output_path": str(scores_path),
            "summary_output_path": str(summary_path),
            "id_column": "SK_ID_CURR",
            "max_rows": 100,
        },
        "monitoring": {
            "input_path": str(input_path),
            "output_path": str(drift_path),
            "id_column": "SK_ID_CURR",
        },
    }
    config_path = tmp_path / "service.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    batch_summary = run_batch_scoring(config_path)
    drift_report = run_drift_monitoring(config_path)

    assert batch_summary["rows_scored"] == 12
    assert scores_path.exists() and summary_path.exists()
    scores = pd.read_parquet(scores_path)
    assert list(scores.columns) == [
        "SK_ID_CURR",
        "default_probability",
        "decision",
        "risk_band",
        "model_version",
        "missing_feature_count",
    ]
    assert drift_report["rows_analyzed"] == 12
    assert drift_path.exists()
    assert json.loads(drift_path.read_text(encoding="utf-8"))["model_version"] == (
        derive_model_version(
            "logistic_regression", {name: "0" * 64 for name in REQUIRED_ARTIFACT_INPUTS}
        )
    )


def test_batch_scoring_enforces_bundle_input_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "model_bundle_path", None)
    bundle_path, training, _ = _bundle_and_reference(
        tmp_path,
        input_contract={"required_features": ["INCOME"], "min_feature_coverage": 0.75},
    )
    batch_input = training.iloc[:2].drop(columns=["INCOME"]).copy()
    batch_input.insert(0, "SK_ID_CURR", [1, 2])
    input_path = tmp_path / "invalid-input.parquet"
    batch_input.to_parquet(input_path, index=False)
    config = {
        "model": {"bundle_path": str(bundle_path)},
        "batch_scoring": {
            "input_path": str(input_path),
            "output_path": str(tmp_path / "scores.parquet"),
            "id_column": "SK_ID_CURR",
            "max_rows": 10,
        },
    }
    config_path = tmp_path / "service.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ValueError, match="Required model features are missing in batch rows"):
        run_batch_scoring(config_path)


def test_build_drift_report_flags_large_numeric_shift(tmp_path):
    _, _, reference = _bundle_and_reference(tmp_path)
    shifted = pd.DataFrame(
        {
            "INCOME": np.full(100, 500_000.0),
            "AGE": np.full(100, 90.0),
            "CONTRACT": ["new-category"] * 100,
        }
    )
    report = build_drift_report(shifted, reference, "v1")
    assert report["status"] == "critical"
    assert report["critical_feature_count"] >= 2
