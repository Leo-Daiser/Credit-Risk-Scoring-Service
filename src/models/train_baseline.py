"""Logistic Regression baseline trainer (Phase 3.1).

This module trains the first *real* ML baseline for the credit-risk scoring
service on top of the final feature dataset produced in Phase 2.3
(``data/processed/train_features.parquet``).

Design goals:

* All reusable logic lives in ``src/`` (no notebook-as-production logic).
* A single ``sklearn`` :class:`~sklearn.pipeline.Pipeline` handles preprocessing
  (imputation + scaling/one-hot) and the estimator, so the whole thing can be
  pickled and reused for inference later.
* Training is deterministic (fixed ``random_seed``) and uses a stratified
  train/validation split.
* The trainer persists three artifacts: the fitted model, a metrics JSON and a
  feature-schema JSON.

We never fabricate metrics: the metrics JSON is only written from a genuine fit
on whatever data the user provides. Real Kaggle data is not required to be
present in this repo — the data-dependent CLI command (``train-baseline``) is
meant to be run locally by the user, while the unit tests exercise the full
pipeline on small synthetic data.

NOT implemented here (by design, until later phases): CatBoost / LightGBM
challengers, calibration, SHAP / reason codes, the API ``/score`` endpoint,
PostgreSQL inference logging, batch scoring and drift monitoring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DEFAULT_ID_COLUMN = "SK_ID_CURR"
DEFAULT_TARGET_COLUMN = "TARGET"

# Thresholds reported in the metrics JSON for operating-point analysis.
THRESHOLD_GRID = [0.2, 0.3, 0.5, 0.7]

_REQUIRED_CONFIG_KEYS = (
    "train_features_path",
    "id_column",
    "target_column",
    "validation_size",
    "random_seed",
    "max_iter",
    "model_output_path",
    "metrics_output_path",
    "feature_schema_output_path",
)


def load_train_config(config_path: str | Path) -> dict[str, Any]:
    """Load and validate the training config, ensuring a ``baseline`` section.

    Args:
        config_path: Path to ``configs/train.yaml``.

    Returns:
        The full parsed configuration dictionary (the caller reads the
        ``baseline`` section from it).

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config is malformed or the section / keys are missing.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Train config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("Train config must be a dictionary.")

    if "baseline" not in config:
        raise ValueError("Train config must contain a 'baseline' section.")

    baseline_config = config["baseline"]
    if not isinstance(baseline_config, dict):
        raise ValueError("Train config 'baseline' must be a dictionary.")

    for required_key in _REQUIRED_CONFIG_KEYS:
        if required_key not in baseline_config:
            raise ValueError(f"Train config 'baseline' must contain '{required_key}'.")

    return config


def load_training_data(path: str | Path) -> pd.DataFrame:
    """Read the training feature parquet file into a DataFrame.

    Raises:
        FileNotFoundError: With a clear message if the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Training feature file not found: {path}. Build it first with "
            "`python -m src.cli build-full-features`."
        )
    return pd.read_parquet(path)


def split_features_target(
    df: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    target_column: str = DEFAULT_TARGET_COLUMN,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Split a training table into the feature matrix ``X`` and target ``y``.

    The id column and the target column are excluded from ``X``.

    Validation:

    * ``id_column`` must exist and must not contain duplicates.
    * ``target_column`` must exist and may only contain the binary values
      ``{0, 1}`` (missing target values are not allowed).

    Returns:
        A ``(X, y, feature_names)`` tuple.

    Raises:
        ValueError: If any validation rule is violated.
    """
    if id_column not in df.columns:
        raise ValueError(f"Training data is missing the id column '{id_column}'.")
    if target_column not in df.columns:
        raise ValueError(
            f"Training data is missing the target column '{target_column}'."
        )

    if df[id_column].duplicated().any():
        duplicate_count = int(df[id_column].duplicated().sum())
        raise ValueError(
            f"Training data contains {duplicate_count} duplicate "
            f"'{id_column}' values; the key contract requires it to be unique."
        )

    target = df[target_column]
    if target.isna().any():
        raise ValueError(
            f"Target column '{target_column}' contains missing values; only "
            "binary values {0, 1} are allowed."
        )

    unique_values = set(pd.unique(target))
    if not unique_values.issubset({0, 1}):
        raise ValueError(
            f"Target column '{target_column}' must only contain binary values "
            f"{{0, 1}}; found {sorted(unique_values)}."
        )

    feature_names = [c for c in df.columns if c not in (id_column, target_column)]
    X = df[feature_names].copy()
    y = target.astype("int64").copy()
    return X, y, feature_names


def infer_feature_types(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Split feature columns into numeric and categorical groups.

    A column is treated as *numeric* when its dtype is a numeric kind
    (int / float). Everything else — ``object``, pandas ``category`` and
    ``bool`` columns — is treated as *categorical* and routed to the
    one-hot-encoding branch of the preprocessor. Treating booleans as
    categorical keeps the encoding explicit (two indicator columns) and avoids
    silently scaling 0/1 flags.

    The returned lists are deterministic: they preserve the column order of
    ``X``.

    Returns:
        A ``(numeric_features, categorical_features)`` tuple.
    """
    numeric_features: list[str] = []
    categorical_features: list[str] = []
    for column in X.columns:
        dtype = X[column].dtype
        if pd.api.types.is_bool_dtype(dtype):
            # Booleans are categorical (explicit one-hot), not numeric.
            categorical_features.append(column)
        elif pd.api.types.is_numeric_dtype(dtype):
            numeric_features.append(column)
        else:
            categorical_features.append(column)
    return numeric_features, categorical_features


def build_logistic_regression_pipeline(
    numeric_features: list[str],
    categorical_features: list[str],
    max_iter: int = 1000,
    random_seed: int = 42,
) -> Pipeline:
    """Build the preprocessing + Logistic Regression pipeline.

    * Numeric branch: median imputation followed by standard scaling.
    * Categorical branch: most-frequent imputation followed by one-hot
      encoding (``handle_unknown="ignore"`` so unseen categories at inference
      time are encoded as all-zeros).
    * Estimator: a class-balanced :class:`LogisticRegression` using the
      ``saga`` solver.

    Returns:
        An unfitted :class:`~sklearn.pipeline.Pipeline`.
    """
    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "onehot",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric_transformer, numeric_features),
            ("categorical", categorical_transformer, categorical_features),
        ],
        remainder="drop",
    )

    classifier = LogisticRegression(
        max_iter=max_iter,
        class_weight="balanced",
        random_state=random_seed,
        solver="saga",
        n_jobs=-1,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


def evaluate_binary_classifier(
    y_true: Any,
    y_proba: Any,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Compute binary-classification metrics from probabilities.

    Args:
        y_true: Ground-truth binary labels.
        y_proba: Predicted probabilities for the positive class.
        threshold: Decision threshold for the headline (point) metrics.

    Returns:
        A dictionary with probability-based metrics (``roc_auc``, ``pr_auc``,
        ``brier_score``), threshold-based metrics at ``threshold`` (``f1``,
        ``precision``, ``recall``, ``confusion_matrix``, ``predicted_positive_rate``),
        the empirical ``positive_rate`` and a ``threshold_metrics`` block with
        precision/recall/f1/predicted_positive_rate across a small grid of
        thresholds.
    """
    y_true = np.asarray(y_true).astype(int)
    y_proba = np.asarray(y_proba, dtype="float64")

    y_pred = (y_proba >= threshold).astype(int)

    roc_auc = float(roc_auc_score(y_true, y_proba))
    pr_auc = float(average_precision_score(y_true, y_proba))
    brier = float(brier_score_loss(y_true, y_proba))

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

    metrics: dict[str, Any] = {
        "threshold": float(threshold),
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "brier_score": brier,
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
        "positive_rate": float(np.mean(y_true)),
        "predicted_positive_rate": float(np.mean(y_pred)),
    }

    threshold_metrics: dict[str, dict[str, float]] = {}
    for thr in THRESHOLD_GRID:
        pred = (y_proba >= thr).astype(int)
        threshold_metrics[f"{thr:.2f}"] = {
            "precision": float(precision_score(y_true, pred, zero_division=0)),
            "recall": float(recall_score(y_true, pred, zero_division=0)),
            "f1": float(f1_score(y_true, pred, zero_division=0)),
            "predicted_positive_rate": float(np.mean(pred)),
        }
    metrics["threshold_metrics"] = threshold_metrics

    return metrics


def save_json(data: dict[str, Any], output_path: str | Path) -> None:
    """Write ``data`` as pretty-printed UTF-8 JSON, creating parent dirs."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_model(model: Any, output_path: str | Path) -> None:
    """Persist a fitted model with joblib, creating parent dirs."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_path)


def build_feature_schema(
    feature_names: list[str],
    numeric_features: list[str],
    categorical_features: list[str],
    id_column: str,
    target_column: str,
) -> dict[str, Any]:
    """Build a serialisable description of the feature contract.

    The schema documents exactly which columns the model expects (and their
    numeric/categorical split) so inference code can validate inputs later.
    """
    return {
        "id_column": id_column,
        "target_column": target_column,
        "total_feature_count": len(feature_names),
        "numeric_feature_count": len(numeric_features),
        "categorical_feature_count": len(categorical_features),
        "numeric_features": list(numeric_features),
        "categorical_features": list(categorical_features),
        "feature_names": list(feature_names),
    }


def train_logistic_regression_baseline(
    config_path: str | Path = "configs/train.yaml",
) -> dict[str, Any]:
    """Train and persist the Logistic Regression baseline end-to-end.

    Pipeline: load config -> load training data -> split X/y -> infer feature
    types -> stratified train/validation split -> build pipeline -> fit ->
    predict validation probabilities -> evaluate -> save model, metrics JSON and
    feature-schema JSON.

    Returns:
        A summary dictionary with row counts, feature-type counts, headline
        validation metrics (``roc_auc`` / ``pr_auc``) and the artifact paths.
    """
    config = load_train_config(config_path)
    baseline_config = config["baseline"]

    id_column = baseline_config["id_column"]
    target_column = baseline_config["target_column"]
    validation_size = baseline_config["validation_size"]
    random_seed = baseline_config["random_seed"]
    max_iter = baseline_config["max_iter"]
    model_output_path = baseline_config["model_output_path"]
    metrics_output_path = baseline_config["metrics_output_path"]
    feature_schema_output_path = baseline_config["feature_schema_output_path"]

    df = load_training_data(baseline_config["train_features_path"])

    X, y, feature_names = split_features_target(
        df, id_column=id_column, target_column=target_column
    )
    numeric_features, categorical_features = infer_feature_types(X)

    X_train, X_valid, y_train, y_valid = train_test_split(
        X,
        y,
        test_size=validation_size,
        random_state=random_seed,
        stratify=y,
    )

    pipeline = build_logistic_regression_pipeline(
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        max_iter=max_iter,
        random_seed=random_seed,
    )
    pipeline.fit(X_train, y_train)

    valid_proba = pipeline.predict_proba(X_valid)[:, 1]
    metrics = evaluate_binary_classifier(y_valid, valid_proba)

    feature_schema = build_feature_schema(
        feature_names=feature_names,
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        id_column=id_column,
        target_column=target_column,
    )

    metrics_payload = {
        "model_type": "logistic_regression_baseline",
        "train_rows": int(len(X_train)),
        "valid_rows": int(len(X_valid)),
        "feature_count": len(feature_names),
        "numeric_feature_count": len(numeric_features),
        "categorical_feature_count": len(categorical_features),
        "random_seed": random_seed,
        "validation_size": validation_size,
        "metrics": metrics,
    }

    save_model(pipeline, model_output_path)
    save_json(metrics_payload, metrics_output_path)
    save_json(feature_schema, feature_schema_output_path)

    return {
        "model_type": "logistic_regression_baseline",
        "train_rows": int(len(X_train)),
        "valid_rows": int(len(X_valid)),
        "feature_count": len(feature_names),
        "numeric_feature_count": len(numeric_features),
        "categorical_feature_count": len(categorical_features),
        "roc_auc": metrics["roc_auc"],
        "pr_auc": metrics["pr_auc"],
        "model_output_path": str(model_output_path),
        "metrics_output_path": str(metrics_output_path),
        "feature_schema_output_path": str(feature_schema_output_path),
    }
