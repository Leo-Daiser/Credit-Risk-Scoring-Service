from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, log_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.core.config import settings

TARGETS = {"clicked_flag", "approved_flag", "issued_flag"}
EXCLUDED_COLUMNS = {
    "impression_id",
    "profile_id",
    "clicked_flag",
    "application_started_flag",
    "application_submitted_flag",
    "approved_flag",
    "issued_flag",
    "commission_amount",
}


def _save_json(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _top_k_metrics(frame: pd.DataFrame, probabilities: np.ndarray) -> dict[str, float]:
    ranked = frame.assign(_probability=probabilities).sort_values(
        ["profile_id", "_probability"], ascending=[True, False]
    )
    result: dict[str, float] = {}
    for label, prefix in (
        ("clicked_flag", "ctr"),
        ("approved_flag", "approval"),
        ("issued_flag", "issued"),
    ):
        if label not in frame:
            continue
        for k in (1, 3, 5):
            top = ranked.groupby("profile_id", sort=False).head(k)
            result[f"{prefix}@{k}"] = float(top[label].mean()) if len(top) else 0.0
    if "commission_amount" in frame:
        for k in (1, 3, 5):
            top = ranked.groupby("profile_id", sort=False).head(k)
            result[f"expected_revenue@{k}"] = float(top["commission_amount"].mean())
    return result


def train_offer_ranker(
    *,
    dataset_path: str | Path | None = None,
    target: str = "clicked_flag",
    model_path: str | Path | None = None,
    metrics_path: str | Path | None = None,
    report_path: str | Path | None = None,
    min_samples: int | None = None,
) -> dict[str, Any]:
    if target not in TARGETS:
        raise ValueError(f"Unsupported target: {target}")
    dataset = Path(dataset_path or settings.offer_ranking_dataset_path)
    model_output = Path(model_path or settings.offer_ranker_model_path)
    metrics_output = Path(metrics_path or settings.offer_ranker_metrics_path)
    report_output = Path(report_path or settings.offer_ranker_report_path)
    required = min_samples or settings.offer_ranker_min_samples
    if not dataset.exists():
        report = {"status": "insufficient_data", "reason": "Dataset does not exist."}
        _save_json(report_output, report)
        return report
    frame = pd.read_parquet(dataset)
    if len(frame) < required or target not in frame or frame[target].nunique() < 2:
        report = {
            "status": "insufficient_data",
            "reason": "Minimum rows and both target classes are required.",
            "rows": len(frame),
            "minimum_rows": required,
            "target": target,
        }
        _save_json(report_output, report)
        return report
    if "profile_id" not in frame or frame["profile_id"].nunique() < 2:
        report = {
            "status": "insufficient_data",
            "reason": "At least two distinct profiles are required for a group split.",
            "rows": len(frame),
            "target": target,
        }
        _save_json(report_output, report)
        return report
    feature_columns = [column for column in frame.columns if column not in EXCLUDED_COLUMNS]
    features = frame[feature_columns]
    labels = frame[target].astype(int)
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_index, evaluation_index = next(
        splitter.split(features, labels, groups=frame["profile_id"])
    )
    train_features = features.iloc[train_index]
    evaluation_features = features.iloc[evaluation_index]
    train_labels = labels.iloc[train_index]
    evaluation_labels = labels.iloc[evaluation_index]
    if train_labels.nunique() < 2 or evaluation_labels.nunique() < 2:
        report = {
            "status": "insufficient_data",
            "reason": "Both group-split partitions must contain both target classes.",
            "rows": len(frame),
            "target": target,
        }
        _save_json(report_output, report)
        return report
    categorical = list(features.select_dtypes(include=["object", "string"]).columns)
    numeric = [column for column in features.columns if column not in categorical]
    preprocessor = ColumnTransformer(
        [
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),
            ("numeric", "passthrough", numeric),
        ]
    )
    pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            (
                "classifier",
                HistGradientBoostingClassifier(max_iter=100, learning_rate=0.05, random_state=42),
            ),
        ]
    )
    pipeline.fit(train_features, train_labels)
    probabilities = pipeline.predict_proba(evaluation_features)[:, 1]
    evaluation_frame = frame.iloc[evaluation_index].copy()
    metrics = {
        "target": target,
        "rows": len(frame),
        "train_rows": len(train_index),
        "evaluation_rows": len(evaluation_index),
        "split_strategy": "group_shuffle_by_profile_id",
        "roc_auc": float(roc_auc_score(evaluation_labels, probabilities)),
        "pr_auc": float(average_precision_score(evaluation_labels, probabilities)),
        "log_loss": float(log_loss(evaluation_labels, probabilities)),
        "calibration_curve": [
            {
                "lower": lower,
                "upper": lower + 0.1,
                "mean_prediction": float(probabilities[(probabilities >= lower) & (probabilities < lower + 0.1)].mean()),
                "observed_rate": float(
                    evaluation_labels[
                        (probabilities >= lower) & (probabilities < lower + 0.1)
                    ].mean()
                ),
            }
            for lower in np.arange(0.0, 1.0, 0.1)
            if ((probabilities >= lower) & (probabilities < lower + 0.1)).any()
        ],
        "top_k": _top_k_metrics(evaluation_frame, probabilities),
        "segments": {
            column: evaluation_frame.groupby(column)[target]
            .agg(["count", "mean"])
            .to_dict("index")
            for column in ("risk_band", "pti_band", "income_band")
            if column in frame
        },
    }
    artifact = {
        "pipeline": pipeline,
        "feature_columns": feature_columns,
        "target": target,
        "format_version": 1,
    }
    model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_output)
    _save_json(metrics_output, metrics)
    report = {
        "status": "trained",
        "model_path": str(model_output),
        "metrics_path": str(metrics_output),
        "target": target,
        "production_enabled": settings.offer_ranker_mode == "ml",
    }
    _save_json(report_output, report)
    return report


def evaluate_offer_ranker(metrics_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(metrics_path or settings.offer_ranker_metrics_path)
    if not path.exists():
        return {"status": "unavailable", "reason": "Metrics artifact does not exist."}
    return {"status": "ready", "metrics": json.loads(path.read_text(encoding="utf-8"))}
