"""CatBoost challenger training on the final feature dataset."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from src.models.train_baseline import (
    DEFAULT_THRESHOLD_GRID,
    build_feature_schema,
    evaluate_binary_classifier,
    infer_feature_types,
    load_train_config,
    load_training_data,
    save_json,
    save_model,
    select_best_threshold,
    split_features_target,
    summarize_probabilities,
)


class CatBoostFramePreprocessor(BaseEstimator, TransformerMixin):
    """Keep a DataFrame while normalising numeric and categorical dtypes."""

    def __init__(self, numeric_features: list[str], categorical_features: list[str]):
        self.numeric_features = numeric_features
        self.categorical_features = categorical_features

    @property
    def feature_names(self) -> list[str]:
        return list(self.numeric_features) + list(self.categorical_features)

    def fit(self, X: pd.DataFrame, y: Any = None) -> CatBoostFramePreprocessor:
        missing = sorted(set(self.feature_names) - set(X.columns))
        if missing:
            raise ValueError(f"CatBoost input is missing features: {missing[:10]}.")
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        frame = X.reindex(columns=self.feature_names).copy()
        for column in self.numeric_features:
            frame[column] = (
                pd.to_numeric(frame[column], errors="coerce")
                .replace([np.inf, -np.inf], np.nan)
                .astype(float)
            )
        for column in self.categorical_features:
            frame[column] = frame[column].fillna("__MISSING__").astype(str)
        return frame

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return np.asarray(self.feature_names, dtype=object)


def build_catboost_pipeline(
    numeric_features: list[str],
    categorical_features: list[str],
    random_seed: int = 42,
    **parameters: Any,
) -> Pipeline:
    defaults: dict[str, Any] = {
        "iterations": 500,
        "depth": 7,
        "learning_rate": 0.05,
        "loss_function": "Logloss",
        "eval_metric": "AUC",
        "auto_class_weights": "Balanced",
        "random_seed": random_seed,
        "thread_count": -1,
        "verbose": False,
        "allow_writing_files": False,
    }
    defaults.update(parameters)
    classifier = CatBoostClassifier(
        cat_features=list(categorical_features),
        **defaults,
    )
    return Pipeline(
        [
            (
                "preprocessor",
                CatBoostFramePreprocessor(numeric_features, categorical_features),
            ),
            ("classifier", classifier),
        ]
    )


def train_catboost_challenger(
    config_path: str | Path = "configs/train.yaml",
) -> dict[str, Any]:
    """Train, evaluate and persist the configured CatBoost challenger."""
    config = load_train_config(config_path)
    challenger = config.get("catboost_challenger")
    if not isinstance(challenger, dict):
        raise ValueError("Train config must contain a 'catboost_challenger' section.")
    required = (
        "train_features_path",
        "id_column",
        "target_column",
        "validation_size",
        "random_seed",
        "model_output_path",
        "metrics_output_path",
        "feature_schema_output_path",
    )
    missing = [key for key in required if key not in challenger]
    if missing:
        raise ValueError(f"CatBoost challenger config is missing keys: {missing}.")

    data = load_training_data(challenger["train_features_path"])
    X, y, feature_names = split_features_target(
        data,
        id_column=challenger["id_column"],
        target_column=challenger["target_column"],
    )
    numeric_features, categorical_features = infer_feature_types(X)
    X_train, X_valid, y_train, y_valid = train_test_split(
        X,
        y,
        test_size=float(challenger["validation_size"]),
        random_state=int(challenger["random_seed"]),
        stratify=y,
    )
    parameters = challenger.get("catboost") or {}
    if not isinstance(parameters, dict):
        raise ValueError("catboost_challenger.catboost must be a dictionary.")
    pipeline = build_catboost_pipeline(
        numeric_features,
        categorical_features,
        random_seed=int(challenger["random_seed"]),
        **parameters,
    )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, module="catboost")
        pipeline.fit(X_train, y_train)

    probability = pipeline.predict_proba(X_valid)[:, 1]
    thresholds = [float(value) for value in challenger.get("thresholds", DEFAULT_THRESHOLD_GRID)]
    metrics = evaluate_binary_classifier(y_valid, probability, thresholds=thresholds)
    selection = select_best_threshold(
        metrics["threshold_metrics"],
        metric_name=str(challenger.get("selected_threshold_metric", "f1")),
    )
    classifier = pipeline.named_steps["classifier"]
    importances = classifier.get_feature_importance()
    top_indices = np.argsort(importances)[::-1][:30]
    processed_feature_names = numeric_features + categorical_features
    top_features = [
        {"feature": processed_feature_names[index], "importance": float(importances[index])}
        for index in top_indices
    ]
    schema = build_feature_schema(
        feature_names,
        numeric_features,
        categorical_features,
        challenger["id_column"],
        challenger["target_column"],
    )
    payload = {
        "model_type": "catboost_challenger",
        "train_rows": int(len(X_train)),
        "valid_rows": int(len(X_valid)),
        "feature_count": len(feature_names),
        "numeric_feature_count": len(numeric_features),
        "categorical_feature_count": len(categorical_features),
        "random_seed": int(challenger["random_seed"]),
        "validation_size": float(challenger["validation_size"]),
        "catboost": classifier.get_params(),
        "metrics": metrics,
        "threshold_selection": selection,
        "probability_summary": summarize_probabilities(probability),
        "top_feature_importances": top_features,
    }
    save_model(pipeline, challenger["model_output_path"])
    save_json(payload, challenger["metrics_output_path"])
    save_json(schema, challenger["feature_schema_output_path"])
    return {
        "model_type": payload["model_type"],
        "train_rows": payload["train_rows"],
        "valid_rows": payload["valid_rows"],
        "feature_count": payload["feature_count"],
        "roc_auc": metrics["roc_auc"],
        "pr_auc": metrics["pr_auc"],
        "brier_score": metrics["brier_score"],
        "best_threshold": selection["best_threshold"],
        "model_output_path": str(challenger["model_output_path"]),
        "metrics_output_path": str(challenger["metrics_output_path"]),
        "feature_schema_output_path": str(challenger["feature_schema_output_path"]),
    }
