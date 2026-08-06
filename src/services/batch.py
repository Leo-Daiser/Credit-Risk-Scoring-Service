"""File-based batch inference using the same production model bundle as the API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.services.scoring import ScoringService


def load_service_config(path: str | Path = "configs/service.yaml") -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Service config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    if not isinstance(config, dict):
        raise ValueError("Service config must be a dictionary.")
    return config


def read_table(path: str | Path) -> pd.DataFrame:
    table_path = Path(path)
    if not table_path.exists():
        raise FileNotFoundError(f"Input table not found: {table_path}")
    suffix = table_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(table_path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(table_path)
    raise ValueError("Input table must be CSV or parquet.")


def write_table(frame: pd.DataFrame, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()
    if suffix == ".csv":
        frame.to_csv(output_path, index=False)
    elif suffix in {".parquet", ".pq"}:
        frame.to_parquet(output_path, index=False)
    else:
        raise ValueError("Output table must be CSV or parquet.")


def run_batch_scoring(
    config_path: str | Path = "configs/service.yaml",
) -> dict[str, Any]:
    """Score a configured CSV/parquet file and save deterministic outputs."""
    config = load_service_config(config_path)
    batch = config.get("batch_scoring")
    model = config.get("model")
    if not isinstance(batch, dict) or not isinstance(model, dict):
        raise ValueError("Service config requires 'model' and 'batch_scoring' sections.")

    frame = read_table(batch["input_path"])
    if frame.empty:
        raise ValueError("Batch scoring input is empty.")
    max_rows = int(batch.get("max_rows", 100_000))
    if len(frame) > max_rows:
        raise ValueError(f"Batch input has {len(frame)} rows; configured maximum is {max_rows}.")

    id_column = str(batch.get("id_column", "SK_ID_CURR"))
    if id_column not in frame.columns:
        raise ValueError(f"Batch input is missing id column '{id_column}'.")
    if frame[id_column].duplicated().any():
        raise ValueError(f"Batch id column '{id_column}' must be unique.")

    service = ScoringService.from_path(
        model["bundle_path"], top_reason_codes=int(model.get("top_reason_codes", 5))
    )
    raw_features = frame.drop(columns=[id_column]).to_dict(orient="records")
    feature_frame = service.bundle.prepare_frame(raw_features)
    probabilities = service.bundle.predict_default_probability(feature_frame)
    threshold = float(service.bundle.metadata["decision_threshold"])
    output = pd.DataFrame(
        {
            id_column: frame[id_column].to_numpy(),
            "default_probability": probabilities,
            "decision": np.where(probabilities >= threshold, "decline", "approve"),
            "risk_band": [service.bundle.risk_band(float(value)) for value in probabilities],
            "model_version": service.bundle.metadata["model_version"],
            "missing_feature_count": feature_frame.isna().sum(axis=1).to_numpy(),
        }
    )
    write_table(output, batch["output_path"])
    summary = {
        "rows_scored": int(len(output)),
        "model_version": service.bundle.metadata["model_version"],
        "mean_default_probability": float(probabilities.mean()),
        "decline_rate": float((probabilities >= threshold).mean()),
        "output_path": str(batch["output_path"]),
    }
    summary_path = batch.get("summary_output_path")
    if summary_path:
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
