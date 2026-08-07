"""Production model evaluation, threshold policy and acceptance gates."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    roc_auc_score,
)


def bootstrap_metric_intervals(
    y_true: Any,
    probabilities: Any,
    *,
    n_bootstrap: int = 200,
    confidence_level: float = 0.95,
    random_seed: int = 42,
) -> dict[str, dict[str, float]]:
    """Estimate non-parametric confidence intervals for probability metrics."""
    y = np.asarray(y_true, dtype="int64")
    scores = np.asarray(probabilities, dtype="float64")
    if len(y) != len(scores) or len(y) == 0:
        raise ValueError("y_true and probabilities must have equal non-zero length.")
    if n_bootstrap < 20:
        raise ValueError("n_bootstrap must be at least 20.")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be in (0, 1).")

    rng = np.random.default_rng(random_seed)
    values: dict[str, list[float]] = {
        "roc_auc": [],
        "pr_auc": [],
        "brier_score": [],
    }
    for _ in range(n_bootstrap):
        indices = rng.integers(0, len(y), len(y))
        sampled_y = y[indices]
        if np.unique(sampled_y).size < 2:
            continue
        sampled_scores = scores[indices]
        values["roc_auc"].append(float(roc_auc_score(sampled_y, sampled_scores)))
        values["pr_auc"].append(float(average_precision_score(sampled_y, sampled_scores)))
        values["brier_score"].append(float(brier_score_loss(sampled_y, sampled_scores)))

    alpha = (1.0 - confidence_level) / 2.0
    result: dict[str, dict[str, float]] = {}
    for metric, samples in values.items():
        if not samples:
            raise ValueError("Bootstrap samples did not contain both target classes.")
        result[metric] = {
            "lower": float(np.quantile(samples, alpha)),
            "upper": float(np.quantile(samples, 1.0 - alpha)),
            "confidence_level": float(confidence_level),
        }
    return result


def bootstrap_roc_auc_difference(
    y_true: Any,
    candidate_probabilities: Any,
    baseline_probabilities: Any,
    *,
    n_bootstrap: int = 200,
    confidence_level: float = 0.95,
    random_seed: int = 42,
) -> dict[str, float]:
    """Estimate a paired bootstrap interval for candidate-minus-baseline AUC."""
    y = np.asarray(y_true, dtype="int64")
    candidate = np.asarray(candidate_probabilities, dtype="float64")
    baseline = np.asarray(baseline_probabilities, dtype="float64")
    if len(y) == 0 or len(candidate) != len(y) or len(baseline) != len(y):
        raise ValueError("Paired bootstrap inputs must have equal non-zero length.")
    if n_bootstrap < 20:
        raise ValueError("n_bootstrap must be at least 20.")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be in (0, 1).")

    point_estimate = float(roc_auc_score(y, candidate) - roc_auc_score(y, baseline))
    rng = np.random.default_rng(random_seed)
    differences: list[float] = []
    for _ in range(n_bootstrap):
        indices = rng.integers(0, len(y), len(y))
        sampled_y = y[indices]
        if np.unique(sampled_y).size < 2:
            continue
        differences.append(
            float(
                roc_auc_score(sampled_y, candidate[indices])
                - roc_auc_score(sampled_y, baseline[indices])
            )
        )
    if not differences:
        raise ValueError("Bootstrap samples did not contain both target classes.")
    alpha = (1.0 - confidence_level) / 2.0
    return {
        "point_estimate": point_estimate,
        "lower": float(np.quantile(differences, alpha)),
        "upper": float(np.quantile(differences, 1.0 - alpha)),
        "confidence_level": float(confidence_level),
    }


def select_cost_sensitive_threshold(
    threshold_metrics: dict[str, dict[str, Any]],
    *,
    false_negative_cost: float,
    false_positive_cost: float,
    min_recall: float = 0.0,
    max_predicted_positive_rate: float = 1.0,
) -> dict[str, Any]:
    """Choose the feasible threshold with minimum configured business cost."""
    if false_negative_cost <= 0 or false_positive_cost <= 0:
        raise ValueError("Misclassification costs must be positive.")
    if not 0.0 <= min_recall <= 1.0:
        raise ValueError("min_recall must be in [0, 1].")
    if not 0.0 < max_predicted_positive_rate <= 1.0:
        raise ValueError("max_predicted_positive_rate must be in (0, 1].")

    candidates: list[dict[str, Any]] = []
    for threshold_key, metrics in threshold_metrics.items():
        recall = float(metrics["recall"])
        predicted_positive_rate = float(metrics["predicted_positive_rate"])
        if recall < min_recall or predicted_positive_rate > max_predicted_positive_rate:
            continue
        false_negatives = int(metrics["fn"])
        false_positives = int(metrics["fp"])
        cost = false_negatives * float(false_negative_cost) + false_positives * float(
            false_positive_cost
        )
        candidates.append(
            {
                "threshold": float(threshold_key),
                "expected_cost": float(cost),
                "recall": recall,
                "predicted_positive_rate": predicted_positive_rate,
                "metrics": metrics,
            }
        )
    if not candidates:
        raise ValueError(
            "No threshold satisfies the configured recall and predicted-positive-rate constraints."
        )
    selected = min(
        candidates,
        key=lambda item: (
            item["expected_cost"],
            -item["recall"],
            item["predicted_positive_rate"],
        ),
    )
    return {
        "strategy": "expected_cost",
        "best_threshold": selected["threshold"],
        "expected_cost": selected["expected_cost"],
        "false_negative_cost": float(false_negative_cost),
        "false_positive_cost": float(false_positive_cost),
        "min_recall": float(min_recall),
        "max_predicted_positive_rate": float(max_predicted_positive_rate),
        "metrics_at_best_threshold": selected["metrics"],
    }


def evaluate_acceptance_gates(
    calibrated_metrics: dict[str, Any],
    raw_metrics: dict[str, Any],
    confidence_intervals: dict[str, dict[str, float]],
    gates: dict[str, Any],
    *,
    baseline_roc_auc: float | None = None,
    baseline_comparison_interval: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Evaluate explicit model quality gates and return an auditable report."""
    checks: list[dict[str, Any]] = []

    def add_check(name: str, value: float, operator: str, threshold: float) -> None:
        passed = value >= threshold if operator == ">=" else value <= threshold
        checks.append(
            {
                "name": name,
                "value": float(value),
                "operator": operator,
                "threshold": float(threshold),
                "passed": bool(passed),
            }
        )

    add_check(
        "roc_auc",
        float(calibrated_metrics["roc_auc"]),
        ">=",
        float(gates.get("min_roc_auc", 0.0)),
    )
    add_check(
        "roc_auc_ci_lower",
        float(confidence_intervals["roc_auc"]["lower"]),
        ">=",
        float(gates.get("min_roc_auc_ci_lower", 0.0)),
    )
    add_check(
        "pr_auc",
        float(calibrated_metrics["pr_auc"]),
        ">=",
        float(gates.get("min_pr_auc", 0.0)),
    )
    add_check(
        "brier_score",
        float(calibrated_metrics["brier_score"]),
        "<=",
        float(gates.get("max_brier_score", 1.0)),
    )
    add_check(
        "expected_calibration_error",
        float(calibrated_metrics["expected_calibration_error"]),
        "<=",
        float(gates.get("max_expected_calibration_error", 1.0)),
    )
    if bool(gates.get("require_calibration_improvement", True)):
        add_check(
            "calibration_brier_improvement",
            float(raw_metrics["brier_score"] - calibrated_metrics["brier_score"]),
            ">=",
            0.0,
        )
    if baseline_roc_auc is not None:
        add_check(
            "roc_auc_improvement_over_baseline",
            float(calibrated_metrics["roc_auc"] - baseline_roc_auc),
            ">=",
            float(gates.get("min_roc_auc_improvement_over_baseline", 0.0)),
        )
    if baseline_comparison_interval is not None:
        add_check(
            "roc_auc_improvement_ci_lower",
            float(baseline_comparison_interval["lower"]),
            ">=",
            float(gates.get("min_roc_auc_improvement_ci_lower", 0.0)),
        )

    return {
        "status": "passed" if all(check["passed"] for check in checks) else "failed",
        "checks": checks,
    }


def build_subgroup_report(
    frame: pd.DataFrame,
    y_true: Any,
    probabilities: Any,
    *,
    threshold: float,
    min_rows: int = 500,
) -> dict[str, Any]:
    """Report monitoring metrics for gender and age groups without claiming fairness."""
    y = np.asarray(y_true, dtype="int64")
    scores = np.asarray(probabilities, dtype="float64")
    if len(frame) != len(y) or len(y) != len(scores):
        raise ValueError("Subgroup inputs must have equal lengths.")

    group_series: dict[str, pd.Series] = {}
    if "CODE_GENDER" in frame:
        group_series["CODE_GENDER"] = frame["CODE_GENDER"].fillna("__MISSING__").astype(str)
    if "AGE_YEARS" in frame:
        ages = pd.to_numeric(frame["AGE_YEARS"], errors="coerce")
        group_series["AGE_BAND"] = pd.cut(
            ages,
            bins=[0, 30, 40, 50, 60, np.inf],
            labels=["<=30", "31-40", "41-50", "51-60", "60+"],
            include_lowest=True,
        ).astype("object")

    report: dict[str, Any] = {}
    for feature_name, groups in group_series.items():
        group_report: dict[str, Any] = {}
        for group in sorted(str(value) for value in groups.dropna().unique()):
            mask = groups.astype(str).to_numpy() == group
            rows = int(mask.sum())
            if rows < min_rows:
                continue
            group_y = y[mask]
            group_scores = scores[mask]
            predictions = (group_scores >= threshold).astype("int64")
            tn, fp, fn, tp = confusion_matrix(group_y, predictions, labels=[0, 1]).ravel()
            group_report[group] = {
                "rows": rows,
                "positive_rate": float(group_y.mean()),
                "mean_probability": float(group_scores.mean()),
                "predicted_positive_rate": float(predictions.mean()),
                "recall": float(tp / (tp + fn)) if tp + fn else None,
                "false_positive_rate": float(fp / (fp + tn)) if fp + tn else None,
                "roc_auc": (
                    float(roc_auc_score(group_y, group_scores))
                    if np.unique(group_y).size == 2
                    else None
                ),
            }
        report[feature_name] = group_report
    return report
