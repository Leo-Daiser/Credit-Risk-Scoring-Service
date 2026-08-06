import numpy as np
import pandas as pd
import pytest

from src.models.evaluation import (
    bootstrap_metric_intervals,
    bootstrap_roc_auc_difference,
    build_subgroup_report,
    evaluate_acceptance_gates,
    select_cost_sensitive_threshold,
)


def test_bootstrap_metric_intervals_are_bounded_and_deterministic():
    y = np.asarray([0, 0, 0, 1, 1, 1] * 50)
    probability = np.asarray([0.05, 0.1, 0.3, 0.6, 0.8, 0.9] * 50)
    first = bootstrap_metric_intervals(y, probability, n_bootstrap=30, random_seed=7)
    second = bootstrap_metric_intervals(y, probability, n_bootstrap=30, random_seed=7)

    assert first == second
    assert 0.0 <= first["roc_auc"]["lower"] <= first["roc_auc"]["upper"] <= 1.0
    assert 0.0 <= first["brier_score"]["lower"] <= 1.0


def test_paired_bootstrap_detects_candidate_auc_improvement():
    y = np.asarray([0, 0, 0, 1, 1, 1] * 100)
    candidate = np.asarray([0.05, 0.10, 0.20, 0.70, 0.80, 0.95] * 100)
    baseline = np.asarray([0.10, 0.20, 0.70, 0.30, 0.80, 0.90] * 100)

    interval = bootstrap_roc_auc_difference(
        y,
        candidate,
        baseline,
        n_bootstrap=30,
        random_seed=7,
    )

    assert interval["point_estimate"] > 0.0
    assert interval["lower"] > 0.0


def test_cost_sensitive_threshold_respects_operating_constraints():
    metrics = {
        "0.10": {
            "recall": 0.90,
            "predicted_positive_rate": 0.40,
            "fn": 10,
            "fp": 100,
        },
        "0.20": {
            "recall": 0.70,
            "predicted_positive_rate": 0.20,
            "fn": 30,
            "fp": 40,
        },
        "0.30": {
            "recall": 0.40,
            "predicted_positive_rate": 0.10,
            "fn": 60,
            "fp": 10,
        },
    }
    selected = select_cost_sensitive_threshold(
        metrics,
        false_negative_cost=5,
        false_positive_cost=1,
        min_recall=0.6,
        max_predicted_positive_rate=0.25,
    )
    assert selected["best_threshold"] == pytest.approx(0.2)
    assert selected["expected_cost"] == pytest.approx(190)


def test_acceptance_gates_report_failure_without_saving_overclaims():
    calibrated = {
        "roc_auc": 0.76,
        "pr_auc": 0.24,
        "brier_score": 0.08,
        "expected_calibration_error": 0.02,
    }
    raw = {"brier_score": 0.12}
    intervals = {"roc_auc": {"lower": 0.74, "upper": 0.78}}
    report = evaluate_acceptance_gates(
        calibrated,
        raw,
        intervals,
        {
            "min_roc_auc": 0.75,
            "min_roc_auc_ci_lower": 0.75,
            "min_pr_auc": 0.2,
            "max_brier_score": 0.1,
            "max_expected_calibration_error": 0.03,
        },
    )
    assert report["status"] == "failed"
    assert any(
        check["name"] == "roc_auc_ci_lower" and not check["passed"] for check in report["checks"]
    )


def test_subgroup_report_contains_operating_metrics():
    rows = 1200
    frame = pd.DataFrame(
        {
            "CODE_GENDER": ["F"] * 600 + ["M"] * 600,
            "AGE_YEARS": [35] * 300 + [55] * 300 + [35] * 300 + [55] * 300,
        }
    )
    y = np.asarray(([0, 1] * (rows // 2)), dtype="int64")
    probability = np.where(y == 1, 0.8, 0.2)
    report = build_subgroup_report(
        frame,
        y,
        probability,
        threshold=0.5,
        min_rows=100,
    )

    assert set(report["CODE_GENDER"]) == {"F", "M"}
    assert report["CODE_GENDER"]["F"]["recall"] == pytest.approx(1.0)
    assert report["AGE_BAND"]["31-40"]["rows"] == 600
