"""Application-level feature engineering (Phase 2.1).

This module builds the application-level feature dataset for the
Home Credit Default Risk problem. It is intentionally self-contained and
reusable:

- it loads its configuration from ``configs/features.yaml``;
- it cleans the raw ``application_train`` / ``application_test`` tables;
- it derives application-level features using safe division;
- it guarantees that train and test share exactly the same feature columns
  (except ``TARGET``, which is kept on the train side only);
- it persists the resulting feature tables as parquet files.

No model training happens here, and no notebook logic is required — all the
reusable logic lives inside ``src/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.data.load_raw import load_raw_tables

# Default sentinel that Home Credit uses in DAYS_EMPLOYED for applicants
# without employment history. It must be treated as missing.
DEFAULT_DAYS_EMPLOYED_ANOMALY_VALUE = 365243

DEFAULT_ID_COLUMN = "SK_ID_CURR"
DEFAULT_TARGET_COLUMN = "TARGET"

# Columns combined into the EXT_SOURCE_* aggregate features.
EXT_SOURCE_COLUMNS = ["EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3"]

# Number of days in a year used for converting day counts to years.
DAYS_IN_YEAR = 365.25


def load_feature_config(config_path: str | Path) -> dict[str, Any]:
    """Load and validate the feature engineering configuration.

    Args:
        config_path: Path to ``configs/features.yaml``.

    Returns:
        The parsed configuration dictionary.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Feature config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("Feature config must be a dictionary.")

    for required_key in ("id_column", "target_column", "output_paths"):
        if required_key not in config:
            raise ValueError(f"Feature config must contain '{required_key}'.")

    output_paths = config["output_paths"]
    if not isinstance(output_paths, dict):
        raise ValueError("Feature config 'output_paths' must be a dictionary.")

    for required_path in (
        "application_train_features",
        "application_test_features",
    ):
        if required_path not in output_paths:
            raise ValueError(
                f"Feature config 'output_paths' must contain '{required_path}'."
            )

    # Provide a sensible default so callers never have to special-case it.
    config.setdefault(
        "days_employed_anomaly_value", DEFAULT_DAYS_EMPLOYED_ANOMALY_VALUE
    )

    return config


def safe_divide(numerator: Any, denominator: Any) -> Any:
    """Divide ``numerator`` by ``denominator`` without ever raising.

    Division by zero (and the resulting ``inf`` / ``-inf`` / ``nan`` values)
    is replaced with ``NaN``. Works with scalars, numpy arrays and pandas
    Series, preserving the Series index when one is supplied.
    """
    if isinstance(numerator, pd.Series) or isinstance(denominator, pd.Series):
        num = (
            numerator
            if isinstance(numerator, pd.Series)
            else pd.Series(numerator)
        )
        den = (
            denominator
            if isinstance(denominator, pd.Series)
            else pd.Series(denominator)
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            result = num.astype("float64") / den.astype("float64")
        return result.replace([np.inf, -np.inf], np.nan)

    num_arr = np.asarray(numerator, dtype="float64")
    den_arr = np.asarray(denominator, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        result = num_arr / den_arr
    result = np.where(np.isinf(result), np.nan, result)

    if np.isscalar(numerator) and np.isscalar(denominator):
        return float(result)
    return result


def clean_application_table(
    df: pd.DataFrame,
    days_employed_anomaly_value: int = DEFAULT_DAYS_EMPLOYED_ANOMALY_VALUE,
) -> pd.DataFrame:
    """Clean a raw application table.

    - Replaces the ``DAYS_EMPLOYED`` anomaly sentinel with ``NaN``.
    - Replaces ``inf`` / ``-inf`` with ``NaN``.
    - Never drops or reorders rows (row count and ``SK_ID_CURR`` preserved).
    """
    cleaned = df.copy()

    if "DAYS_EMPLOYED" in cleaned.columns:
        cleaned["DAYS_EMPLOYED"] = cleaned["DAYS_EMPLOYED"].replace(
            days_employed_anomaly_value, np.nan
        )

    cleaned = cleaned.replace([np.inf, -np.inf], np.nan)

    return cleaned


def add_application_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived application-level features where source columns exist.

    All ratio features use :func:`safe_divide` to avoid division-by-zero
    errors. Row count and existing columns are preserved.
    """
    out = df.copy()
    columns = set(out.columns)

    def has(*names: str) -> bool:
        return all(name in columns for name in names)

    if has("AMT_CREDIT", "AMT_INCOME_TOTAL"):
        out["CREDIT_INCOME_RATIO"] = safe_divide(
            out["AMT_CREDIT"], out["AMT_INCOME_TOTAL"]
        )

    if has("AMT_ANNUITY", "AMT_INCOME_TOTAL"):
        out["ANNUITY_INCOME_RATIO"] = safe_divide(
            out["AMT_ANNUITY"], out["AMT_INCOME_TOTAL"]
        )

    if has("AMT_ANNUITY", "AMT_CREDIT"):
        out["CREDIT_TERM"] = safe_divide(out["AMT_ANNUITY"], out["AMT_CREDIT"])

    if has("DAYS_EMPLOYED", "DAYS_BIRTH"):
        out["DAYS_EMPLOYED_RATIO"] = safe_divide(
            out["DAYS_EMPLOYED"], out["DAYS_BIRTH"]
        )

    if has("AMT_INCOME_TOTAL", "CNT_FAM_MEMBERS"):
        out["INCOME_PER_FAM_MEMBER"] = safe_divide(
            out["AMT_INCOME_TOTAL"], out["CNT_FAM_MEMBERS"]
        )

    if has("DAYS_BIRTH"):
        out["AGE_YEARS"] = -out["DAYS_BIRTH"] / DAYS_IN_YEAR

    if has("DAYS_EMPLOYED"):
        out["EMPLOYMENT_YEARS"] = -out["DAYS_EMPLOYED"] / DAYS_IN_YEAR

    ext_cols = [c for c in EXT_SOURCE_COLUMNS if c in columns]
    if ext_cols:
        ext = out[ext_cols]
        out["EXT_SOURCE_MEAN"] = ext.mean(axis=1)
        out["EXT_SOURCE_STD"] = ext.std(axis=1)
        out["EXT_SOURCE_MIN"] = ext.min(axis=1)
        out["EXT_SOURCE_MAX"] = ext.max(axis=1)

    # Any inf introduced above is converted to NaN for consistency.
    out = out.replace([np.inf, -np.inf], np.nan)

    return out


def build_application_features(
    application_train: pd.DataFrame,
    application_test: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    target_column: str = DEFAULT_TARGET_COLUMN,
    days_employed_anomaly_value: int = DEFAULT_DAYS_EMPLOYED_ANOMALY_VALUE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build aligned application-level features for train and test.

    Raises:
        ValueError: if the target column is missing from the train table, or
            if the train and test feature columns do not match (ignoring the
            target column).
    """
    if target_column not in application_train.columns:
        raise ValueError(
            f"Train table is missing the target column '{target_column}'."
        )

    train = clean_application_table(application_train, days_employed_anomaly_value)
    test = clean_application_table(application_test, days_employed_anomaly_value)

    train = add_application_derived_features(train)
    test = add_application_derived_features(test)

    # The target must never leak into the test features.
    if target_column in test.columns:
        test = test.drop(columns=[target_column])

    target = train[target_column]
    train_features_only = train.drop(columns=[target_column])

    train_cols = set(train_features_only.columns)
    test_cols = set(test.columns)
    if train_cols != test_cols:
        only_train = sorted(train_cols - test_cols)
        only_test = sorted(test_cols - train_cols)
        raise ValueError(
            "Train/test feature columns do not match. "
            f"Only in train: {only_train}. Only in test: {only_test}."
        )

    # Keep a deterministic, aligned column order across train and test.
    ordered_columns = list(train_features_only.columns)
    test_features = test[ordered_columns].copy()

    train_features = train_features_only[ordered_columns].copy()
    train_features[target_column] = target.to_numpy()

    return train_features, test_features


def save_application_features(
    train_features: pd.DataFrame,
    test_features: pd.DataFrame,
    output_train_path: str | Path,
    output_test_path: str | Path,
) -> tuple[Path, Path]:
    """Persist train/test feature tables as parquet files.

    Parent directories are created if they do not exist.
    """
    train_path = Path(output_train_path)
    test_path = Path(output_test_path)

    train_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)

    train_features.to_parquet(train_path, index=False)
    test_features.to_parquet(test_path, index=False)

    return train_path, test_path


def run_build_application_features(
    data_config_path: str | Path = "configs/data.yaml",
    feature_config_path: str | Path = "configs/features.yaml",
) -> dict[str, Any]:
    """End-to-end entrypoint used by the CLI.

    Loads only the application tables, builds features, saves the parquet
    outputs and returns a small summary dictionary.
    """
    feature_config = load_feature_config(feature_config_path)

    tables = load_raw_tables(
        data_config_path,
        table_names=["application_train", "application_test"],
    )
    application_train = tables["application_train"]
    application_test = tables["application_test"]

    train_features, test_features = build_application_features(
        application_train,
        application_test,
        id_column=feature_config["id_column"],
        target_column=feature_config["target_column"],
        days_employed_anomaly_value=feature_config["days_employed_anomaly_value"],
    )

    output_paths = feature_config["output_paths"]
    train_path, test_path = save_application_features(
        train_features,
        test_features,
        output_paths["application_train_features"],
        output_paths["application_test_features"],
    )

    return {
        "train_shape": train_features.shape,
        "test_shape": test_features.shape,
        "train_path": str(train_path),
        "test_path": str(test_path),
    }
