"""Offline feature drift monitoring against bundle reference statistics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.core.config import settings
from src.services.batch import load_service_config, read_table
from src.services.scoring import load_model_bundle

EPSILON = 1e-6


def population_stability_index(
    reference: np.ndarray | list[float],
    current: np.ndarray | list[float],
) -> float:
    reference_array = np.asarray(reference, dtype="float64")
    current_array = np.asarray(current, dtype="float64")
    if reference_array.shape != current_array.shape or reference_array.size == 0:
        raise ValueError("PSI distributions must have the same non-zero shape.")
    ref = np.clip(reference_array, EPSILON, None)
    cur = np.clip(current_array, EPSILON, None)
    ref = ref / ref.sum()
    cur = cur / cur.sum()
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def numeric_drift(values: pd.Series, reference: dict[str, Any]) -> dict[str, float]:
    numeric = pd.to_numeric(values, errors="coerce")
    non_null = numeric.dropna().to_numpy(dtype="float64")
    edges = [float(value) for value in reference.get("distribution_edges", [])]
    proportions = reference.get("distribution_proportions", [])
    if len(non_null) and proportions:
        counts, _ = np.histogram(non_null, bins=[-np.inf, *edges, np.inf])
        current = counts / max(int(counts.sum()), 1)
        psi = population_stability_index(proportions, current)
    else:
        psi = 0.0
    missing_rate = float(numeric.isna().mean())
    return {
        "psi": psi,
        "missing_rate": missing_rate,
        "missing_rate_delta": abs(missing_rate - float(reference.get("missing_rate", 0.0))),
    }


def categorical_drift(values: pd.Series, reference: dict[str, Any]) -> dict[str, float]:
    categories = list(reference.get("top_frequencies", {}))
    current_values = values.fillna("__MISSING__").astype(str)
    current_frequencies = current_values.value_counts(normalize=True)
    reference_distribution = [float(reference["top_frequencies"][key]) for key in categories]
    current_distribution = [float(current_frequencies.get(key, 0.0)) for key in categories]
    reference_distribution.append(float(reference.get("other_rate", 0.0)))
    current_distribution.append(float(max(0.0, 1.0 - sum(current_distribution))))
    psi = population_stability_index(reference_distribution, current_distribution)
    missing_rate = float(values.isna().mean())
    return {
        "psi": psi,
        "missing_rate": missing_rate,
        "missing_rate_delta": abs(missing_rate - float(reference.get("missing_rate", 0.0))),
    }


def build_drift_report(
    frame: pd.DataFrame,
    reference_stats: dict[str, Any],
    model_version: str,
    psi_warning: float = 0.1,
    psi_critical: float = 0.2,
    missing_rate_warning: float = 0.1,
) -> dict[str, Any]:
    features: dict[str, Any] = {}
    for column, reference in reference_stats.get("numeric", {}).items():
        result = numeric_drift(frame[column], reference)
        features[column] = {"type": "numeric", **result}
    for column, reference in reference_stats.get("categorical", {}).items():
        result = categorical_drift(frame[column], reference)
        features[column] = {"type": "categorical", **result}

    for result in features.values():
        if result["psi"] >= psi_critical:
            severity = "critical"
        elif result["psi"] >= psi_warning or result["missing_rate_delta"] >= missing_rate_warning:
            severity = "warning"
        else:
            severity = "ok"
        result["severity"] = severity

    critical = sorted(name for name, result in features.items() if result["severity"] == "critical")
    warnings = sorted(name for name, result in features.items() if result["severity"] == "warning")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_version": model_version,
        "rows_analyzed": int(len(frame)),
        "status": "critical" if critical else "warning" if warnings else "ok",
        "critical_feature_count": len(critical),
        "warning_feature_count": len(warnings),
        "critical_features": critical,
        "warning_features": warnings,
        "features": features,
    }


def run_drift_monitoring(
    config_path: str | Path = "configs/service.yaml",
) -> dict[str, Any]:
    config = load_service_config(config_path)
    monitoring = config.get("monitoring")
    model = config.get("model")
    if not isinstance(monitoring, dict) or not isinstance(model, dict):
        raise ValueError("Service config requires 'model' and 'monitoring' sections.")
    bundle = load_model_bundle(settings.resolve_model_bundle_path(model.get("bundle_path")))
    raw = read_table(monitoring["input_path"])
    id_column = monitoring.get("id_column", bundle.feature_schema.get("id_column"))
    if id_column in raw.columns:
        raw = raw.drop(columns=[id_column])
    frame = bundle.prepare_frame(raw.to_dict(orient="records"))
    report = build_drift_report(
        frame,
        bundle.reference_stats,
        model_version=bundle.metadata["model_version"],
        psi_warning=float(monitoring.get("psi_warning", 0.1)),
        psi_critical=float(monitoring.get("psi_critical", 0.2)),
        missing_rate_warning=float(monitoring.get("missing_rate_warning", 0.1)),
    )
    output_path = Path(monitoring["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["output_path"] = str(output_path)
    return report
