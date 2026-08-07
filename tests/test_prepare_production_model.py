import json

import joblib
import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.model_selection import train_test_split

from src.models.model_bundle import (
    BUNDLE_FORMAT_VERSION,
    REQUIRED_ARTIFACT_INPUTS,
    ModelBundle,
    derive_model_version,
)
from src.models.prepare_production_model import (
    artifact_version,
    expected_calibration_error,
    prepare_production_model,
    save_production_artifacts_atomically,
    sha256_file,
    validate_source_training_contract,
)
from src.models.train_baseline import (
    build_feature_schema,
    build_logistic_regression_pipeline,
    split_features_target,
)
from src.services.scoring import load_model_bundle


def _training_frame(n: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(17)
    income = rng.normal(150_000, 35_000, n)
    age = rng.integers(21, 70, n)
    contract = rng.choice(["Cash loans", "Revolving loans"], n)
    logit = -2.5 + 0.035 * (50 - age) + 0.7 * (contract == "Cash loans")
    probability = 1.0 / (1.0 + np.exp(-logit))
    target = rng.binomial(1, probability)
    # Ensure both classes remain available in every deterministic split.
    target[:24] = [0, 1] * 12
    return pd.DataFrame(
        {
            "SK_ID_CURR": np.arange(100_000, 100_000 + n),
            "TARGET": target,
            "AMT_INCOME_TOTAL": income,
            "AGE_YEARS": age.astype(float),
            "NAME_CONTRACT_TYPE": contract,
        }
    )


def test_expected_calibration_error_is_zero_for_perfect_bins():
    assert expected_calibration_error([0, 0, 1, 1], [0.0, 0.0, 1.0, 1.0]) == 0.0
    with pytest.raises(ValueError, match="at least 2"):
        expected_calibration_error([0], [0.2], n_bins=1)


def test_model_bundle_aligns_features_and_rejects_unknowns():
    bundle = ModelBundle(
        model=None,
        metadata={
            "risk_bands": [
                {"name": "low", "upper_bound": 0.2},
                {"name": "high", "upper_bound": None},
            ]
        },
        feature_schema={
            "feature_names": ["NUM", "CAT"],
            "numeric_features": ["NUM"],
            "categorical_features": ["CAT"],
        },
        reference_stats={},
    )
    frame = bundle.prepare_frame([{"CAT": "A", "NUM": "2.5"}, {"NUM": None}])
    assert list(frame.columns) == ["NUM", "CAT"]
    assert frame.loc[0, "NUM"] == pytest.approx(2.5)
    assert pd.isna(frame.loc[1, "CAT"])
    assert bundle.risk_band(0.1) == "low"
    assert bundle.risk_band(0.5) == "high"
    with pytest.raises(ValueError, match="Unknown model features"):
        bundle.prepare_frame([{"OTHER": 1}])
    with pytest.raises(ValueError, match="finite numbers"):
        bundle.prepare_frame([{"NUM": "not-a-number"}])
    with pytest.raises(ValueError, match="finite numbers"):
        bundle.prepare_frame([{"NUM": np.inf}])


def test_load_model_bundle_rejects_legacy_contract(tmp_path):
    legacy_bundle = ModelBundle(
        model=None,
        metadata={"model_version": "legacy"},
        feature_schema={"feature_names": ["NUM"]},
        reference_stats={},
    )
    bundle_path = tmp_path / "legacy.joblib"
    joblib.dump(legacy_bundle, bundle_path)

    with pytest.raises(ValueError, match="Unsupported model bundle format"):
        load_model_bundle(bundle_path)


def test_source_training_contract_rejects_split_mismatch():
    schema = {"feature_names": ["NUM", "CAT"]}
    metrics = {
        "model_type": "catboost_challenger",
        "random_seed": 42,
        "validation_size": 0.2,
        "feature_count": 2,
    }
    contract = validate_source_training_contract(
        {"random_seed": 42, "holdout_size": 0.2}, metrics, schema
    )
    assert contract["validation_size"] == pytest.approx(0.2)

    with pytest.raises(ValueError, match="random_seed"):
        validate_source_training_contract({"random_seed": 7, "holdout_size": 0.2}, metrics, schema)
    with pytest.raises(ValueError, match="validation_size"):
        validate_source_training_contract(
            {"random_seed": 42, "holdout_size": 0.25}, metrics, schema
        )


def test_artifact_version_changes_with_any_reproducibility_input():
    fingerprints = {name: "0" * 64 for name in REQUIRED_ARTIFACT_INPUTS}
    original = artifact_version("catboost_calibrated", fingerprints)

    changed = dict(fingerprints)
    changed["training_data_sha256"] = "1" * 64

    assert artifact_version("catboost_calibrated", changed) != original


def test_atomic_bundle_write_preserves_existing_outputs_on_failure(tmp_path, monkeypatch):
    class ProbabilityModel:
        def predict_proba(self, frame):
            return np.tile([0.8, 0.2], (len(frame), 1))

    metadata = {
        "bundle_format_version": BUNDLE_FORMAT_VERSION,
        "model_version": derive_model_version(
            "test", {name: "0" * 64 for name in REQUIRED_ARTIFACT_INPUTS}
        ),
        "model_type": "test",
        "feature_count": 1,
        "decision_threshold": 0.5,
        "risk_bands": [
            {"name": "low", "upper_bound": 0.5},
            {"name": "high", "upper_bound": None},
        ],
        "input_contract": {"required_features": [], "min_feature_coverage": 0.0},
        "artifact_inputs": {name: "0" * 64 for name in REQUIRED_ARTIFACT_INPUTS},
    }
    bundle = ModelBundle(
        model=ProbabilityModel(),
        metadata=metadata,
        feature_schema={
            "feature_names": ["NUM"],
            "numeric_features": ["NUM"],
            "categorical_features": [],
        },
        reference_stats={"numeric": {}, "categorical": {}},
    )
    valid_version = metadata["model_version"]
    bundle.metadata["model_version"] = "tampered-version"
    with pytest.raises(ValueError, match="does not match its artifact_inputs manifest"):
        bundle.validate_contract()
    bundle.metadata["model_version"] = valid_version
    bundle_path = tmp_path / "bundle.joblib"
    metadata_path = tmp_path / "metadata.json"
    bundle_path.write_bytes(b"existing-bundle")
    metadata_path.write_text("existing-metadata", encoding="utf-8")

    def fail_dump(value, path):
        path.write_bytes(b"partial")
        raise OSError("simulated artifact write failure")

    monkeypatch.setattr("src.models.prepare_production_model.joblib.dump", fail_dump)

    with pytest.raises(OSError, match="simulated artifact write failure"):
        save_production_artifacts_atomically(bundle, metadata, bundle_path, metadata_path)

    assert bundle_path.read_bytes() == b"existing-bundle"
    assert metadata_path.read_text(encoding="utf-8") == "existing-metadata"
    assert not list(tmp_path.glob("*.tmp"))


def test_prepare_production_model_end_to_end(tmp_path):
    data = _training_frame()
    train_path = tmp_path / "train.parquet"
    data.to_parquet(train_path, index=False)

    X, y, features = split_features_target(data)
    numeric = ["AMT_INCOME_TOTAL", "AGE_YEARS"]
    categorical = ["NAME_CONTRACT_TYPE"]
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    source_model = build_logistic_regression_pipeline(
        numeric,
        categorical,
        max_iter=500,
        random_seed=42,
        solver="liblinear",
        n_jobs=None,
    )
    source_model.fit(X_train, y_train)

    source_path = tmp_path / "source.joblib"
    source_metrics_path = tmp_path / "source_metrics.json"
    baseline_metrics_path = tmp_path / "baseline_metrics.json"
    baseline_model_path = tmp_path / "baseline.joblib"
    schema_path = tmp_path / "schema.json"
    bundle_path = tmp_path / "bundle.joblib"
    metadata_path = tmp_path / "metadata.json"
    joblib.dump(source_model, source_path)
    joblib.dump(source_model, baseline_model_path)
    schema = build_feature_schema(features, numeric, categorical, "SK_ID_CURR", "TARGET")
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    source_metrics_path.write_text(
        json.dumps(
            {
                "model_type": "logistic_regression_baseline",
                "random_seed": 42,
                "validation_size": 0.2,
                "feature_count": len(features),
            }
        ),
        encoding="utf-8",
    )
    baseline_metrics_path.write_text(
        json.dumps(
            {
                "model_type": "logistic_regression_baseline",
                "random_seed": 42,
                "validation_size": 0.2,
                "feature_count": len(features),
                "metrics": {"roc_auc": 0.0},
            }
        ),
        encoding="utf-8",
    )

    config = {
        "production_model": {
            "source_model_path": str(source_path),
            "source_metrics_path": str(source_metrics_path),
            "baseline_model_path": str(baseline_model_path),
            "baseline_metrics_path": str(baseline_metrics_path),
            "feature_schema_path": str(schema_path),
            "train_features_path": str(train_path),
            "bundle_output_path": str(bundle_path),
            "metadata_output_path": str(metadata_path),
            "random_seed": 42,
            "holdout_size": 0.2,
            "calibration_fraction": 0.5,
            "calibration_cv": 2,
            "input_contract": {
                "required_features": ["AGE_YEARS"],
                "min_feature_coverage": 0.25,
            },
            "thresholds": [0.05, 0.1, 0.2, 0.3],
            "threshold_policy": {
                "strategy": "expected_cost",
                "false_negative_cost": 5.0,
                "false_positive_cost": 1.0,
                "min_recall": 0.0,
                "max_predicted_positive_rate": 1.0,
            },
            "bootstrap_samples": 20,
            "subgroup_min_rows": 10,
            "acceptance_gates": {
                "min_roc_auc": 0.0,
                "min_roc_auc_ci_lower": 0.0,
                "min_pr_auc": 0.0,
                "max_brier_score": 1.0,
                "max_expected_calibration_error": 1.0,
                "min_roc_auc_improvement_over_baseline": 0.0,
                "min_roc_auc_improvement_ci_lower": -1.0,
                "require_calibration_improvement": False,
            },
        }
    }
    config_path = tmp_path / "train.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    summary = prepare_production_model(config_path)

    assert bundle_path.exists()
    assert metadata_path.exists()
    assert summary["training_rows"] == 192
    assert summary["acceptance_status"] == "passed"
    assert summary["calibration_rows"] + summary["evaluation_rows"] == 48
    bundle = joblib.load(bundle_path)
    assert isinstance(bundle, ModelBundle)
    bundle.validate_contract()
    aligned = bundle.prepare_frame([data.loc[0, features].to_dict()])
    probability = bundle.predict_default_probability(aligned)[0]
    assert 0.0 <= probability <= 1.0
    assert bundle.metadata["decision_threshold"] in [0.05, 0.1, 0.2, 0.3]
    assert bundle.metadata["source_training"]["random_seed"] == 42
    assert bundle.metadata["acceptance"]["status"] == "passed"
    assert (
        bundle.metadata["baseline_comparison"]["training_contract"]["model_type"]
        == "logistic_regression_baseline"
    )
    assert set(bundle.metadata["confidence_intervals"]) == {
        "roc_auc",
        "pr_auc",
        "brier_score",
    }
    assert len(bundle.metadata["source_model_sha256"]) == 64
    assert bundle.metadata["bundle_format_version"] == BUNDLE_FORMAT_VERSION
    assert bundle.metadata["input_contract"] == {
        "required_features": ["AGE_YEARS"],
        "min_feature_coverage": 0.25,
    }
    assert set(bundle.metadata["artifact_inputs"]) == REQUIRED_ARTIFACT_INPUTS
    assert bundle.metadata["artifact_inputs"]["training_data_sha256"] == sha256_file(train_path)
    assert set(bundle.reference_stats) == {"numeric", "categorical"}
    assert bundle.reference_stats["numeric"]["AGE_YEARS"]["min"] >= 21
    assert (
        "Cash loans"
        in bundle.reference_stats["categorical"]["NAME_CONTRACT_TYPE"]["allowed_values"]
    )
