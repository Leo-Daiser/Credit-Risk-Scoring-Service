import json

import joblib
import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.model_selection import train_test_split

from src.models.model_bundle import ModelBundle
from src.models.prepare_production_model import (
    expected_calibration_error,
    prepare_production_model,
    validate_source_training_contract,
)
from src.models.train_baseline import (
    build_feature_schema,
    build_logistic_regression_pipeline,
    split_features_target,
)


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
        metadata={"risk_bands": [{"name": "low", "upper_bound": 0.2}, {"name": "high", "upper_bound": None}]},
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
        validate_source_training_contract(
            {"random_seed": 7, "holdout_size": 0.2}, metrics, schema
        )
    with pytest.raises(ValueError, match="validation_size"):
        validate_source_training_contract(
            {"random_seed": 42, "holdout_size": 0.25}, metrics, schema
        )


def test_prepare_production_model_end_to_end(tmp_path):
    data = _training_frame()
    train_path = tmp_path / "train.parquet"
    data.to_parquet(train_path, index=False)

    X, y, features = split_features_target(data)
    numeric = ["AMT_INCOME_TOTAL", "AGE_YEARS"]
    categorical = ["NAME_CONTRACT_TYPE"]
    X_train, _, y_train, _ = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
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
    schema_path = tmp_path / "schema.json"
    bundle_path = tmp_path / "bundle.joblib"
    metadata_path = tmp_path / "metadata.json"
    joblib.dump(source_model, source_path)
    schema = build_feature_schema(
        features, numeric, categorical, "SK_ID_CURR", "TARGET"
    )
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

    config = {
        "production_model": {
            "source_model_path": str(source_path),
            "source_metrics_path": str(source_metrics_path),
            "feature_schema_path": str(schema_path),
            "train_features_path": str(train_path),
            "bundle_output_path": str(bundle_path),
            "metadata_output_path": str(metadata_path),
            "random_seed": 42,
            "holdout_size": 0.2,
            "calibration_fraction": 0.5,
            "calibration_cv": 2,
            "thresholds": [0.05, 0.1, 0.2, 0.3],
        }
    }
    config_path = tmp_path / "train.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    summary = prepare_production_model(config_path)

    assert bundle_path.exists()
    assert metadata_path.exists()
    assert summary["training_rows"] == 192
    assert summary["calibration_rows"] + summary["evaluation_rows"] == 48
    bundle = joblib.load(bundle_path)
    assert isinstance(bundle, ModelBundle)
    aligned = bundle.prepare_frame([data.loc[0, features].to_dict()])
    probability = bundle.predict_default_probability(aligned)[0]
    assert 0.0 <= probability <= 1.0
    assert bundle.metadata["decision_threshold"] in [0.05, 0.1, 0.2, 0.3]
    assert bundle.metadata["source_training"]["random_seed"] == 42
    assert len(bundle.metadata["source_model_sha256"]) == 64
    assert set(bundle.reference_stats) == {"numeric", "categorical"}
