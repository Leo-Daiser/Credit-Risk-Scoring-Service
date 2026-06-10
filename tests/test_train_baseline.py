"""Tests for the Phase 3.1 Logistic Regression baseline trainer."""

import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.pipeline import Pipeline

from src.models.train_baseline import (
    build_feature_schema,
    build_logistic_regression_pipeline,
    evaluate_binary_classifier,
    infer_feature_types,
    split_features_target,
    train_logistic_regression_baseline,
)


# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------
def _synthetic_training_frame(n: int = 200, seed: int = 0) -> pd.DataFrame:
    """Small but separable synthetic dataset with both target classes."""
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 2, size=n)
    # Numeric feature correlated with the target plus noise.
    num1 = y + rng.normal(0, 0.5, size=n)
    num2 = rng.normal(0, 1, size=n)
    # Categorical feature correlated with the target.
    cat = np.where(
        y == 1,
        rng.choice(["a", "b"], size=n, p=[0.8, 0.2]),
        rng.choice(["a", "b"], size=n, p=[0.2, 0.8]),
    )
    return pd.DataFrame(
        {
            "SK_ID_CURR": np.arange(1, n + 1),
            "TARGET": y.astype("int64"),
            "NUM_FEATURE_1": num1,
            "NUM_FEATURE_2": num2,
            "CAT_FEATURE": cat,
        }
    )


# ---------------------------------------------------------------------------
# split_features_target
# ---------------------------------------------------------------------------
def test_split_features_target_drops_id_and_target():
    df = _synthetic_training_frame(n=20)
    X, y, feature_names = split_features_target(df)
    assert "SK_ID_CURR" not in X.columns
    assert "TARGET" not in X.columns
    assert feature_names == ["NUM_FEATURE_1", "NUM_FEATURE_2", "CAT_FEATURE"]
    assert len(X) == len(y) == 20


def test_split_features_target_missing_id_raises():
    df = _synthetic_training_frame(n=20).drop(columns=["SK_ID_CURR"])
    with pytest.raises(ValueError, match="missing the id column"):
        split_features_target(df)


def test_split_features_target_missing_target_raises():
    df = _synthetic_training_frame(n=20).drop(columns=["TARGET"])
    with pytest.raises(ValueError, match="missing the target column"):
        split_features_target(df)


def test_split_features_target_duplicate_id_raises():
    df = _synthetic_training_frame(n=20)
    df.loc[1, "SK_ID_CURR"] = df.loc[0, "SK_ID_CURR"]
    with pytest.raises(ValueError, match="duplicate"):
        split_features_target(df)


def test_split_features_target_invalid_target_values_raises():
    df = _synthetic_training_frame(n=20)
    df.loc[0, "TARGET"] = 2
    with pytest.raises(ValueError, match="binary values"):
        split_features_target(df)


# ---------------------------------------------------------------------------
# infer_feature_types
# ---------------------------------------------------------------------------
def test_infer_feature_types_detects_numeric_and_categorical():
    df = _synthetic_training_frame(n=20)
    df["BOOL_FEATURE"] = True
    X, _, _ = split_features_target(df)
    numeric, categorical = infer_feature_types(X)
    assert "NUM_FEATURE_1" in numeric
    assert "NUM_FEATURE_2" in numeric
    assert "CAT_FEATURE" in categorical
    # Booleans are routed to the categorical (one-hot) branch.
    assert "BOOL_FEATURE" in categorical


# ---------------------------------------------------------------------------
# build_logistic_regression_pipeline
# ---------------------------------------------------------------------------
def test_build_logistic_regression_pipeline_returns_pipeline():
    pipeline = build_logistic_regression_pipeline(
        numeric_features=["NUM_FEATURE_1"],
        categorical_features=["CAT_FEATURE"],
        max_iter=500,
        random_seed=42,
    )
    assert isinstance(pipeline, Pipeline)
    assert "preprocessor" in pipeline.named_steps
    assert "classifier" in pipeline.named_steps
    classifier = pipeline.named_steps["classifier"]
    assert classifier.max_iter == 500
    assert classifier.class_weight == "balanced"


# ---------------------------------------------------------------------------
# evaluate_binary_classifier
# ---------------------------------------------------------------------------
def test_evaluate_binary_classifier_outputs_required_metrics():
    y_true = [0, 0, 1, 1, 0, 1]
    y_proba = [0.1, 0.4, 0.8, 0.7, 0.2, 0.9]
    metrics = evaluate_binary_classifier(y_true, y_proba)
    for key in (
        "roc_auc",
        "pr_auc",
        "f1",
        "precision",
        "recall",
        "brier_score",
        "confusion_matrix",
        "positive_rate",
        "predicted_positive_rate",
        "threshold_metrics",
    ):
        assert key in metrics
    assert set(metrics["confusion_matrix"]) == {"tn", "fp", "fn", "tp"}
    for thr in ("0.20", "0.30", "0.50", "0.70"):
        assert thr in metrics["threshold_metrics"]
        assert "precision" in metrics["threshold_metrics"][thr]


# ---------------------------------------------------------------------------
# build_feature_schema
# ---------------------------------------------------------------------------
def test_build_feature_schema_contains_expected_fields():
    schema = build_feature_schema(
        feature_names=["NUM_FEATURE_1", "CAT_FEATURE"],
        numeric_features=["NUM_FEATURE_1"],
        categorical_features=["CAT_FEATURE"],
        id_column="SK_ID_CURR",
        target_column="TARGET",
    )
    assert schema["id_column"] == "SK_ID_CURR"
    assert schema["target_column"] == "TARGET"
    assert schema["total_feature_count"] == 2
    assert schema["numeric_feature_count"] == 1
    assert schema["categorical_feature_count"] == 1
    assert schema["numeric_features"] == ["NUM_FEATURE_1"]
    assert schema["categorical_features"] == ["CAT_FEATURE"]
    assert schema["feature_names"] == ["NUM_FEATURE_1", "CAT_FEATURE"]


# ---------------------------------------------------------------------------
# train_logistic_regression_baseline (end-to-end on synthetic data)
# ---------------------------------------------------------------------------
def test_train_logistic_regression_baseline_end_to_end_on_synthetic_data(tmp_path):
    df = _synthetic_training_frame(n=200, seed=1)
    train_path = tmp_path / "train_features.parquet"
    df.to_parquet(train_path, index=False)

    model_path = tmp_path / "models" / "logreg.joblib"
    metrics_path = tmp_path / "metrics" / "metrics.json"
    schema_path = tmp_path / "reports" / "schema.json"

    config = {
        "baseline": {
            "train_features_path": str(train_path),
            "id_column": "SK_ID_CURR",
            "target_column": "TARGET",
            "validation_size": 0.2,
            "random_seed": 42,
            "max_iter": 1000,
            "model_output_path": str(model_path),
            "metrics_output_path": str(metrics_path),
            "feature_schema_output_path": str(schema_path),
        }
    }
    config_path = tmp_path / "train.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    summary = train_logistic_regression_baseline(config_path=config_path)

    assert model_path.exists()
    assert metrics_path.exists()
    assert schema_path.exists()
    assert "roc_auc" in summary
    assert "pr_auc" in summary
    assert summary["model_type"] == "logistic_regression_baseline"
    assert summary["train_rows"] + summary["valid_rows"] == 200
