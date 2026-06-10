"""Logistic Regression baseline trainer (Phase 3.1 + 3.1.1 hardening).

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
* The trainer persists four artifacts: the fitted model, a metrics JSON, a
  feature-schema JSON and a richer evaluation-report JSON.

Phase 3.1.1 hardening adds:

* fully configurable Logistic Regression hyper-parameters
  (``baseline.logistic_regression.*``);
* convergence-warning capture (training never crashes on a sklearn
  ``ConvergenceWarning`` — the flag and messages are recorded instead);
* configurable evaluation thresholds with full confusion counts per threshold;
* automatic best-threshold selection by a configurable metric;
* a probability summary (quantiles) and sklearn classification reports at both
  the default and the selected thresholds;
* a standalone evaluation-report JSON artifact.

We never fabricate metrics: every JSON is only written from a genuine fit on
whatever data the user provides. Real Kaggle data is not required to be present
in this repo — the data-dependent CLI command (``train-baseline``) is meant to
be run locally by the user, while the unit tests exercise the full pipeline on
small synthetic data.

NOT implemented here (by design, until later phases): CatBoost / LightGBM
challengers, calibration, SHAP / reason codes, the API ``/score`` endpoint,
PostgreSQL inference logging, batch scoring and drift monitoring.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    classification_report,
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

# Default decision thresholds reported in the metrics / evaluation JSON for
# operating-point analysis. The config can override these.
DEFAULT_THRESHOLD_GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

# Default Logistic Regression hyper-parameters; each can be overridden via
# ``baseline.logistic_regression.*`` in the config.
DEFAULT_LOGISTIC_REGRESSION_PARAMS: dict[str, Any] = {
    "max_iter": 1000,
    "solver": "saga",
    "class_weight": "balanced",
    "n_jobs": -1,
    "C": 1.0,
}

DEFAULT_SELECTED_THRESHOLD_METRIC = "f1"

# Maximum number of encoded one-hot feature names to sample into the metrics /
# evaluation report (we never dump thousands of names).
ENCODED_FEATURE_NAME_SAMPLE_SIZE = 30

# Only the truly essential config keys are required; everything else has a
# sensible default so older configs and synthetic-test configs keep working.
_REQUIRED_CONFIG_KEYS = (
    "train_features_path",
    "id_column",
    "target_column",
    "validation_size",
    "random_seed",
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


def resolve_logistic_regression_params(
    baseline_config: dict[str, Any],
) -> dict[str, Any]:
    """Resolve Logistic Regression hyper-parameters from the baseline config.

    Reads the nested ``baseline.logistic_regression`` block, falling back to a
    legacy top-level ``max_iter`` (for backward compatibility) and finally to
    :data:`DEFAULT_LOGISTIC_REGRESSION_PARAMS`. Missing fields keep their
    defaults.
    """
    lr_config = baseline_config.get("logistic_regression") or {}
    if not isinstance(lr_config, dict):
        raise ValueError(
            "Train config 'baseline.logistic_regression' must be a dictionary."
        )

    params = dict(DEFAULT_LOGISTIC_REGRESSION_PARAMS)
    # Backward compatibility: honour a legacy top-level max_iter if present.
    if "max_iter" in baseline_config:
        params["max_iter"] = baseline_config["max_iter"]
    for key in DEFAULT_LOGISTIC_REGRESSION_PARAMS:
        if key in lr_config:
            params[key] = lr_config[key]
    return params


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
    solver: str = "saga",
    class_weight: Any = "balanced",
    n_jobs: int | None = -1,
    C: float = 1.0,
) -> Pipeline:
    """Build the preprocessing + Logistic Regression pipeline.

    * Numeric branch: median imputation followed by standard scaling.
    * Categorical branch: most-frequent imputation followed by one-hot
      encoding (``handle_unknown="ignore"`` so unseen categories at inference
      time are encoded as all-zeros).
    * Estimator: a (by default class-balanced) :class:`LogisticRegression`.

    All Logistic Regression hyper-parameters (``max_iter``, ``solver``,
    ``class_weight``, ``n_jobs``, ``C``) are configurable; defaults match the
    Phase 3.1 baseline.

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
        class_weight=class_weight,
        random_state=random_seed,
        solver=solver,
        n_jobs=n_jobs,
        C=C,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


def _threshold_key(threshold: float) -> str:
    """Stable string key for a threshold (e.g. ``0.3`` -> ``"0.30"``)."""
    return f"{float(threshold):.2f}"


def evaluate_binary_classifier(
    y_true: Any,
    y_proba: Any,
    threshold: float = 0.5,
    thresholds: list[float] | None = None,
) -> dict[str, Any]:
    """Compute binary-classification metrics from probabilities.

    Args:
        y_true: Ground-truth binary labels.
        y_proba: Predicted probabilities for the positive class.
        threshold: Decision threshold for the headline (point) metrics.
        thresholds: Optional grid of thresholds for the per-threshold block.
            Defaults to :data:`DEFAULT_THRESHOLD_GRID`.

    Returns:
        A dictionary with probability-based metrics (``roc_auc``, ``pr_auc``,
        ``brier_score``), threshold-based metrics at ``threshold`` (``f1``,
        ``precision``, ``recall``, ``confusion_matrix``,
        ``predicted_positive_rate``), the empirical ``positive_rate`` and a
        ``threshold_metrics`` block. Each entry of ``threshold_metrics``
        contains ``precision``, ``recall``, ``f1``, ``predicted_positive_rate``
        and the raw confusion counts ``tp`` / ``fp`` / ``tn`` / ``fn``.
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLD_GRID

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
    for thr in thresholds:
        pred = (y_proba >= thr).astype(int)
        t_tn, t_fp, t_fn, t_tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
        threshold_metrics[_threshold_key(thr)] = {
            "precision": float(precision_score(y_true, pred, zero_division=0)),
            "recall": float(recall_score(y_true, pred, zero_division=0)),
            "f1": float(f1_score(y_true, pred, zero_division=0)),
            "predicted_positive_rate": float(np.mean(pred)),
            "tp": int(t_tp),
            "fp": int(t_fp),
            "tn": int(t_tn),
            "fn": int(t_fn),
        }
    metrics["threshold_metrics"] = threshold_metrics

    return metrics


def select_best_threshold(
    threshold_metrics: dict[str, dict[str, float]],
    metric_name: str = "f1",
) -> dict[str, Any]:
    """Pick the threshold that maximises ``metric_name``.

    Args:
        threshold_metrics: Mapping of threshold key -> per-threshold metrics
            (as produced by :func:`evaluate_binary_classifier`).
        metric_name: Metric to maximise (e.g. ``"f1"``, ``"precision"``).

    Returns:
        A dictionary with ``metric_name``, ``best_threshold`` (float),
        ``best_metric_value`` and ``metrics_at_best_threshold``.

    Raises:
        ValueError: If ``threshold_metrics`` is empty or no entry contains the
            requested metric.
    """
    if not threshold_metrics:
        raise ValueError("threshold_metrics is empty; cannot select a threshold.")

    best_key: str | None = None
    best_value = -np.inf
    for key, entry in threshold_metrics.items():
        if metric_name not in entry:
            continue
        value = float(entry[metric_name])
        if value > best_value:
            best_value = value
            best_key = key

    if best_key is None:
        raise ValueError(f"No threshold entry contained the metric '{metric_name}'.")

    return {
        "metric_name": metric_name,
        "best_threshold": float(best_key),
        "best_metric_value": float(best_value),
        "metrics_at_best_threshold": dict(threshold_metrics[best_key]),
    }


def summarize_probabilities(y_proba: Any) -> dict[str, float]:
    """Summarise a vector of predicted probabilities.

    Returns:
        A dictionary with ``min``, ``max``, ``mean``, ``std`` and the
        percentiles ``p01``, ``p05``, ``p25``, ``p50``, ``p75``, ``p95``,
        ``p99``.
    """
    arr = np.asarray(y_proba, dtype="float64")
    percentiles = {
        "p01": 1,
        "p05": 5,
        "p25": 25,
        "p50": 50,
        "p75": 75,
        "p95": 95,
        "p99": 99,
    }
    summary: dict[str, float] = {
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
    }
    for name, q in percentiles.items():
        summary[name] = float(np.percentile(arr, q))
    return summary


def compute_encoded_feature_info(pipeline: Pipeline) -> dict[str, Any]:
    """Best-effort extraction of the encoded (transformed) feature space.

    Uses ``preprocessor.get_feature_names_out()``. Returns the encoded feature
    count and a small sample of names (never the full list for wide OHE spaces).
    Failures are swallowed and reported as ``encoded_feature_count = None``.
    """
    info: dict[str, Any] = {
        "encoded_feature_count": None,
        "encoded_feature_names_sample": [],
    }
    try:
        preprocessor = pipeline.named_steps["preprocessor"]
        names = list(preprocessor.get_feature_names_out())
        info["encoded_feature_count"] = len(names)
        info["encoded_feature_names_sample"] = names[:ENCODED_FEATURE_NAME_SAMPLE_SIZE]
    except Exception:  # pragma: no cover - defensive, never crash training
        pass
    return info


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


def _fit_with_convergence_capture(
    pipeline: Pipeline,
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> dict[str, Any]:
    """Fit ``pipeline`` while capturing sklearn ConvergenceWarnings.

    Training is never aborted because of a :class:`ConvergenceWarning`; instead
    the flag and the unique warning messages are recorded and returned.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        pipeline.fit(X_train, y_train)

    messages: list[str] = []
    saw_convergence_warning = False
    for warning in caught:
        if issubclass(warning.category, ConvergenceWarning):
            saw_convergence_warning = True
            message = str(warning.message)
            if message not in messages:
                messages.append(message)

    classifier = pipeline.named_steps["classifier"]
    n_iter = getattr(classifier, "n_iter_", None)
    if n_iter is not None:
        n_iter = [int(v) for v in np.asarray(n_iter).ravel().tolist()]

    return {
        "convergence_warning": saw_convergence_warning,
        "convergence_warning_messages": messages,
        "n_iter": n_iter,
    }


def train_logistic_regression_baseline(
    config_path: str | Path = "configs/train.yaml",
) -> dict[str, Any]:
    """Train and persist the Logistic Regression baseline end-to-end.

    Pipeline: load config -> load training data -> split X/y -> infer feature
    types -> stratified train/validation split -> build pipeline -> fit (with
    convergence capture) -> predict validation probabilities -> evaluate ->
    select best threshold -> save model, metrics JSON, feature-schema JSON and
    evaluation-report JSON.

    Returns:
        A summary dictionary with row counts, feature-type counts, encoded
        feature count, headline validation metrics, the selected best threshold,
        the convergence flag and all artifact paths.
    """
    config = load_train_config(config_path)
    baseline_config = config["baseline"]

    id_column = baseline_config["id_column"]
    target_column = baseline_config["target_column"]
    validation_size = baseline_config["validation_size"]
    random_seed = baseline_config["random_seed"]
    model_output_path = baseline_config["model_output_path"]
    metrics_output_path = baseline_config["metrics_output_path"]
    feature_schema_output_path = baseline_config["feature_schema_output_path"]

    # Optional with default: evaluation report lives next to the feature schema.
    evaluation_report_output_path = baseline_config.get("evaluation_report_output_path")
    if not evaluation_report_output_path:
        evaluation_report_output_path = str(
            Path(feature_schema_output_path).with_name(
                "logistic_regression_baseline_evaluation_report.json"
            )
        )

    thresholds = baseline_config.get("thresholds") or DEFAULT_THRESHOLD_GRID
    thresholds = [float(t) for t in thresholds]
    selected_threshold_metric = baseline_config.get(
        "selected_threshold_metric", DEFAULT_SELECTED_THRESHOLD_METRIC
    )

    lr_params = resolve_logistic_regression_params(baseline_config)

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
        max_iter=lr_params["max_iter"],
        random_seed=random_seed,
        solver=lr_params["solver"],
        class_weight=lr_params["class_weight"],
        n_jobs=lr_params["n_jobs"],
        C=lr_params["C"],
    )

    convergence_info = _fit_with_convergence_capture(pipeline, X_train, y_train)

    valid_proba = pipeline.predict_proba(X_valid)[:, 1]
    metrics = evaluate_binary_classifier(
        y_valid, valid_proba, threshold=0.5, thresholds=thresholds
    )

    threshold_selection = select_best_threshold(
        metrics["threshold_metrics"], metric_name=selected_threshold_metric
    )
    best_threshold = threshold_selection["best_threshold"]

    probability_summary = summarize_probabilities(valid_proba)
    encoded_info = compute_encoded_feature_info(pipeline)

    y_pred_default = (valid_proba >= 0.5).astype(int)
    y_pred_best = (valid_proba >= best_threshold).astype(int)
    classification_report_default = classification_report(
        np.asarray(y_valid).astype(int),
        y_pred_default,
        output_dict=True,
        zero_division=0,
    )
    classification_report_best = classification_report(
        np.asarray(y_valid).astype(int),
        y_pred_best,
        output_dict=True,
        zero_division=0,
    )

    lr_hyperparameters = {
        "max_iter": lr_params["max_iter"],
        "solver": lr_params["solver"],
        "C": lr_params["C"],
        "class_weight": lr_params["class_weight"],
        "n_jobs": lr_params["n_jobs"],
        "n_iter": convergence_info["n_iter"],
    }

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
        "encoded_feature_count": encoded_info["encoded_feature_count"],
        "encoded_feature_names_sample": encoded_info["encoded_feature_names_sample"],
        "random_seed": random_seed,
        "validation_size": validation_size,
        "logistic_regression": lr_hyperparameters,
        "convergence_warning": convergence_info["convergence_warning"],
        "convergence_warning_messages": convergence_info[
            "convergence_warning_messages"
        ],
        "metrics": metrics,
        "threshold_selection": threshold_selection,
        "probability_summary": probability_summary,
    }

    evaluation_report = {
        "model_type": "logistic_regression_baseline",
        "train_rows": int(len(X_train)),
        "valid_rows": int(len(X_valid)),
        "feature_count": len(feature_names),
        "numeric_feature_count": len(numeric_features),
        "categorical_feature_count": len(categorical_features),
        "encoded_feature_count": encoded_info["encoded_feature_count"],
        "convergence_warning": convergence_info["convergence_warning"],
        "convergence_warning_messages": convergence_info[
            "convergence_warning_messages"
        ],
        "logistic_regression": lr_hyperparameters,
        "metrics": metrics,
        "threshold_selection": threshold_selection,
        "probability_summary": probability_summary,
        "classification_report_default_threshold": classification_report_default,
        "classification_report_best_threshold": classification_report_best,
    }

    save_model(pipeline, model_output_path)
    save_json(metrics_payload, metrics_output_path)
    save_json(feature_schema, feature_schema_output_path)
    save_json(evaluation_report, evaluation_report_output_path)

    return {
        "model_type": "logistic_regression_baseline",
        "train_rows": int(len(X_train)),
        "valid_rows": int(len(X_valid)),
        "feature_count": len(feature_names),
        "numeric_feature_count": len(numeric_features),
        "categorical_feature_count": len(categorical_features),
        "encoded_feature_count": encoded_info["encoded_feature_count"],
        "roc_auc": metrics["roc_auc"],
        "pr_auc": metrics["pr_auc"],
        "best_threshold": best_threshold,
        "best_threshold_metric": threshold_selection["metric_name"],
        "best_threshold_metric_value": threshold_selection["best_metric_value"],
        "convergence_warning": convergence_info["convergence_warning"],
        "model_output_path": str(model_output_path),
        "metrics_output_path": str(metrics_output_path),
        "feature_schema_output_path": str(feature_schema_output_path),
        "evaluation_report_output_path": str(evaluation_report_output_path),
    }
