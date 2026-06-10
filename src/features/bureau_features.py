"""Bureau & bureau_balance historical aggregation layer (Phase 2.2).

This module builds applicant-level (``SK_ID_CURR``) features from the Home
Credit ``bureau`` and ``bureau_balance`` tables. The resulting table is
designed to be merged into the application-level feature set by ``SK_ID_CURR``.

Pipeline:

1. :func:`aggregate_bureau_balance` rolls ``bureau_balance`` up to one row per
   ``SK_ID_BUREAU`` (status counts / ratios, DPD and bad-debt features).
2. :func:`merge_bureau_with_balance_features` left-joins those loan-level
   features onto ``bureau`` without changing the bureau row count.
3. :func:`aggregate_bureau_to_applicant` aggregates the enriched ``bureau``
   table up to one row per ``SK_ID_CURR`` (counts, ratios, numeric
   aggregations, derived debt features and bureau-balance roll-ups).

No model training happens here, and no notebook logic is required — all the
reusable logic lives inside ``src/``. Real Kaggle CSVs and the generated
parquet output are never committed (see ``.gitignore``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.data.load_raw import load_raw_tables
from src.features.application_features import safe_divide

DEFAULT_ID_COLUMN = "SK_ID_CURR"
DEFAULT_BUREAU_ID_COLUMN = "SK_ID_BUREAU"

# All bureau_balance STATUS categories used by the Home Credit dataset.
BUREAU_BALANCE_STATUSES = ["0", "1", "2", "3", "4", "5", "C", "X"]
# Statuses representing some level of days-past-due (delinquency).
BUREAU_BALANCE_DPD_STATUSES = ["1", "2", "3", "4", "5"]
# Status representing a written-off / bad-debt month.
BUREAU_BALANCE_BAD_DEBT_STATUS = "5"

# Numeric bureau columns aggregated at applicant level (only when present).
BUREAU_NUMERIC_COLUMNS = [
    "DAYS_CREDIT",
    "CREDIT_DAY_OVERDUE",
    "DAYS_CREDIT_ENDDATE",
    "DAYS_ENDDATE_FACT",
    "AMT_CREDIT_MAX_OVERDUE",
    "CNT_CREDIT_PROLONG",
    "AMT_CREDIT_SUM",
    "AMT_CREDIT_SUM_DEBT",
    "AMT_CREDIT_SUM_LIMIT",
    "AMT_CREDIT_SUM_OVERDUE",
    "DAYS_CREDIT_UPDATE",
    "AMT_ANNUITY",
]
BUREAU_NUMERIC_AGGS = ["mean", "max", "min", "sum", "std"]

# CREDIT_ACTIVE category -> applicant-level loan count column.
BUREAU_CREDIT_ACTIVE_FEATURES = {
    "Active": "BUREAU_ACTIVE_LOAN_COUNT",
    "Closed": "BUREAU_CLOSED_LOAN_COUNT",
    "Bad debt": "BUREAU_BAD_DEBT_LOAN_COUNT",
    "Sold": "BUREAU_SOLD_LOAN_COUNT",
}

# CREDIT_ACTIVE count column -> applicant-level ratio column.
BUREAU_CREDIT_ACTIVE_RATIOS = {
    "BUREAU_ACTIVE_LOAN_COUNT": "BUREAU_ACTIVE_LOAN_RATIO",
    "BUREAU_CLOSED_LOAN_COUNT": "BUREAU_CLOSED_LOAN_RATIO",
    "BUREAU_BAD_DEBT_LOAN_COUNT": "BUREAU_BAD_DEBT_LOAN_RATIO",
    "BUREAU_SOLD_LOAN_COUNT": "BUREAU_SOLD_LOAN_RATIO",
}

# CREDIT_TYPE category -> applicant-level count column (safe, deterministic).
BUREAU_CREDIT_TYPE_FEATURES = {
    "Consumer credit": "BUREAU_CREDIT_TYPE_CONSUMER_CREDIT_COUNT",
    "Credit card": "BUREAU_CREDIT_TYPE_CREDIT_CARD_COUNT",
    "Car loan": "BUREAU_CREDIT_TYPE_CAR_LOAN_COUNT",
    "Mortgage": "BUREAU_CREDIT_TYPE_MORTGAGE_COUNT",
}

# Aggregations used to roll bureau_balance loan-level features up to applicant.
BUREAU_BALANCE_ROLLUP_AGGS = ["mean", "max", "sum"]


def load_bureau_feature_config(config_path: str | Path) -> dict[str, Any]:
    """Load and validate the feature config, ensuring a ``bureau_features`` section.

    Args:
        config_path: Path to ``configs/features.yaml``.

    Returns:
        The full parsed configuration dictionary (the caller reads the
        ``bureau_features`` section from it).
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Feature config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("Feature config must be a dictionary.")

    if "bureau_features" not in config:
        raise ValueError("Feature config must contain a 'bureau_features' section.")

    bureau_config = config["bureau_features"]
    if not isinstance(bureau_config, dict):
        raise ValueError("Feature config 'bureau_features' must be a dictionary.")

    for required_key in ("id_column", "bureau_id_column", "output_path"):
        if required_key not in bureau_config:
            raise ValueError(
                f"Feature config 'bureau_features' must contain '{required_key}'."
            )

    return config


def aggregate_bureau_balance(
    bureau_balance: pd.DataFrame,
    bureau_id_column: str = DEFAULT_BUREAU_ID_COLUMN,
) -> pd.DataFrame:
    """Aggregate ``bureau_balance`` to one row per ``SK_ID_BUREAU``.

    Produces deterministic status counts/ratios as well as DPD and bad-debt
    features. Missing statuses always yield zero counts/ratios (never missing
    columns), and all ratios use safe division.
    """
    if bureau_id_column not in bureau_balance.columns:
        raise ValueError(
            f"bureau_balance is missing the id column '{bureau_id_column}'."
        )

    df = bureau_balance.copy()
    df["STATUS"] = df["STATUS"].astype(str).str.strip()

    grouped = df.groupby(bureau_id_column, sort=True)
    months_count = grouped.size().rename("BUREAU_BALANCE_MONTHS_COUNT")

    result = pd.DataFrame(index=months_count.index)
    result["BUREAU_BALANCE_MONTHS_COUNT"] = months_count.astype("int64")

    if "MONTHS_BALANCE" in df.columns:
        result["BUREAU_BALANCE_MONTHS_MIN"] = grouped["MONTHS_BALANCE"].min()
        result["BUREAU_BALANCE_MONTHS_MAX"] = grouped["MONTHS_BALANCE"].max()
    else:
        result["BUREAU_BALANCE_MONTHS_MIN"] = np.nan
        result["BUREAU_BALANCE_MONTHS_MAX"] = np.nan

    status_counts = (
        df.groupby([bureau_id_column, "STATUS"]).size().unstack(fill_value=0)
    )

    months = result["BUREAU_BALANCE_MONTHS_COUNT"]
    for status in BUREAU_BALANCE_STATUSES:
        count_col = f"BUREAU_BALANCE_STATUS_{status}_COUNT"
        if status in status_counts.columns:
            counts = status_counts[status].reindex(result.index).fillna(0)
        else:
            counts = pd.Series(0, index=result.index)
        result[count_col] = counts.astype("int64")
        result[f"BUREAU_BALANCE_STATUS_{status}_RATIO"] = safe_divide(
            result[count_col], months
        )

    dpd_count = sum(
        result[f"BUREAU_BALANCE_STATUS_{s}_COUNT"] for s in BUREAU_BALANCE_DPD_STATUSES
    )
    result["BUREAU_BALANCE_DPD_COUNT"] = dpd_count.astype("int64")
    result["BUREAU_BALANCE_DPD_RATIO"] = safe_divide(
        result["BUREAU_BALANCE_DPD_COUNT"], months
    )

    bad_debt_col = f"BUREAU_BALANCE_STATUS_{BUREAU_BALANCE_BAD_DEBT_STATUS}_COUNT"
    result["BUREAU_BALANCE_BAD_DEBT_COUNT"] = result[bad_debt_col].astype("int64")
    result["BUREAU_BALANCE_BAD_DEBT_RATIO"] = safe_divide(
        result["BUREAU_BALANCE_BAD_DEBT_COUNT"], months
    )

    result = result.replace([np.inf, -np.inf], np.nan)
    result = result.reset_index()
    return result


def merge_bureau_with_balance_features(
    bureau: pd.DataFrame,
    bureau_balance_features: pd.DataFrame,
    bureau_id_column: str = DEFAULT_BUREAU_ID_COLUMN,
) -> pd.DataFrame:
    """Left-join loan-level bureau_balance features onto ``bureau``.

    The bureau row count is preserved (no row explosion). Loans without any
    bureau_balance history get ``0`` for count/ratio columns.
    """
    if bureau_id_column not in bureau.columns:
        raise ValueError(f"bureau is missing the id column '{bureau_id_column}'.")

    n_before = len(bureau)
    merged = bureau.merge(bureau_balance_features, on=bureau_id_column, how="left")

    balance_cols = [c for c in bureau_balance_features.columns if c != bureau_id_column]
    for col in balance_cols:
        if col in merged.columns and ("COUNT" in col or "RATIO" in col):
            merged[col] = merged[col].fillna(0)

    if len(merged) != n_before:
        raise ValueError(
            "merge_bureau_with_balance_features changed the bureau row count "
            f"({n_before} -> {len(merged)}); check for duplicate SK_ID_BUREAU."
        )

    return merged


def _categorical_counts(
    df: pd.DataFrame,
    id_column: str,
    source_column: str,
    mapping: dict[str, str],
    index: pd.Index,
) -> pd.DataFrame:
    """Count rows per applicant for selected categories of ``source_column``."""
    counts = pd.DataFrame(index=index)
    if source_column in df.columns:
        values = df[source_column].astype(str).str.strip()
        for category, out_col in mapping.items():
            flag = (values == category).astype("int64")
            counts[out_col] = flag.groupby(df[id_column]).sum()
    else:
        for out_col in mapping.values():
            counts[out_col] = 0
    return counts.fillna(0).astype("int64")


def aggregate_bureau_to_applicant(
    bureau_enriched: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    bureau_id_column: str = DEFAULT_BUREAU_ID_COLUMN,
) -> pd.DataFrame:
    """Aggregate the enriched ``bureau`` table to one row per ``SK_ID_CURR``.

    The output has ``SK_ID_CURR`` as the first column, no duplicate applicants,
    deterministic (sorted) feature column order, and no infinities.
    """
    if id_column not in bureau_enriched.columns:
        raise ValueError(f"bureau is missing the id column '{id_column}'.")

    df = bureau_enriched.replace([np.inf, -np.inf], np.nan).copy()

    grouped = df.groupby(id_column, sort=True)
    features = pd.DataFrame(index=grouped.size().index)

    # --- Basic loan counts -------------------------------------------------
    features["BUREAU_LOAN_COUNT"] = grouped.size().astype("int64")
    active_counts = _categorical_counts(
        df, id_column, "CREDIT_ACTIVE", BUREAU_CREDIT_ACTIVE_FEATURES, features.index
    )
    features = features.join(active_counts)

    loan_count = features["BUREAU_LOAN_COUNT"]
    for count_col, ratio_col in BUREAU_CREDIT_ACTIVE_RATIOS.items():
        features[ratio_col] = safe_divide(features[count_col], loan_count)

    # --- Credit type counts ------------------------------------------------
    credit_type_counts = _categorical_counts(
        df, id_column, "CREDIT_TYPE", BUREAU_CREDIT_TYPE_FEATURES, features.index
    )
    features = features.join(credit_type_counts)

    # --- Numeric aggregations ---------------------------------------------
    numeric_cols = [c for c in BUREAU_NUMERIC_COLUMNS if c in df.columns]
    if numeric_cols:
        numeric_agg = grouped[numeric_cols].agg(BUREAU_NUMERIC_AGGS)
        numeric_agg.columns = [
            f"BUREAU_{col}_{stat.upper()}" for col, stat in numeric_agg.columns
        ]
        features = features.join(numeric_agg)

    # --- Derived debt features --------------------------------------------
    def _group_sum(col: str) -> pd.Series:
        if col in df.columns:
            return grouped[col].sum()
        return pd.Series(0.0, index=features.index)

    total_credit = _group_sum("AMT_CREDIT_SUM")
    total_debt = _group_sum("AMT_CREDIT_SUM_DEBT")
    total_overdue = _group_sum("AMT_CREDIT_SUM_OVERDUE")
    features["BUREAU_TOTAL_CREDIT_SUM"] = total_credit
    features["BUREAU_TOTAL_DEBT"] = total_debt
    features["BUREAU_TOTAL_OVERDUE"] = total_overdue
    features["BUREAU_DEBT_CREDIT_RATIO"] = safe_divide(total_debt, total_credit)
    features["BUREAU_OVERDUE_DEBT_RATIO"] = safe_divide(total_overdue, total_debt)

    # A loan is "overdue" if it has positive overdue days or a positive
    # overdue amount.
    overdue_flag = pd.Series(False, index=df.index)
    if "CREDIT_DAY_OVERDUE" in df.columns:
        overdue_flag = overdue_flag | (df["CREDIT_DAY_OVERDUE"].fillna(0) > 0)
    if "AMT_CREDIT_SUM_OVERDUE" in df.columns:
        overdue_flag = overdue_flag | (df["AMT_CREDIT_SUM_OVERDUE"].fillna(0) > 0)
    overdue_count = overdue_flag.astype("int64").groupby(df[id_column]).sum()
    overdue_count = overdue_count.reindex(features.index).fillna(0).astype("int64")
    features["BUREAU_OVERDUE_LOAN_COUNT"] = overdue_count
    features["BUREAU_OVERDUE_LOAN_RATIO"] = safe_divide(overdue_count, loan_count)
    features["BUREAU_HAS_OVERDUE_FLAG"] = (overdue_count > 0).astype("int64")

    # --- Bureau balance roll-up (loan level -> applicant level) ------------
    balance_cols = sorted(c for c in df.columns if c.startswith("BUREAU_BALANCE_"))
    if balance_cols:
        rollup = grouped[balance_cols].agg(BUREAU_BALANCE_ROLLUP_AGGS)
        rollup.columns = [f"{col}_{stat.upper()}" for col, stat in rollup.columns]
        features = features.join(rollup)

    # --- Finalize ----------------------------------------------------------
    features = features.replace([np.inf, -np.inf], np.nan)

    features = features.reset_index()
    feature_columns = sorted(c for c in features.columns if c != id_column)
    features = features[[id_column, *feature_columns]].reset_index(drop=True)

    return features


def build_bureau_features(
    bureau: pd.DataFrame,
    bureau_balance: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    bureau_id_column: str = DEFAULT_BUREAU_ID_COLUMN,
) -> pd.DataFrame:
    """Orchestrate the full bureau feature pipeline.

    Runs :func:`aggregate_bureau_balance`,
    :func:`merge_bureau_with_balance_features` and
    :func:`aggregate_bureau_to_applicant` in order, returning one row per
    ``SK_ID_CURR``.
    """
    balance_features = aggregate_bureau_balance(bureau_balance, bureau_id_column)
    bureau_enriched = merge_bureau_with_balance_features(
        bureau, balance_features, bureau_id_column
    )
    return aggregate_bureau_to_applicant(
        bureau_enriched,
        id_column=id_column,
        bureau_id_column=bureau_id_column,
    )


def save_bureau_features(
    bureau_features: pd.DataFrame,
    output_path: str | Path,
) -> None:
    """Persist the applicant-level bureau features as a parquet file.

    Parent directories are created if they do not exist.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bureau_features.to_parquet(output_path, index=False)


def run_build_bureau_features(
    data_config_path: str | Path = "configs/data.yaml",
    feature_config_path: str | Path = "configs/features.yaml",
) -> dict[str, Any]:
    """End-to-end entrypoint used by the CLI.

    Loads only the ``bureau`` and ``bureau_balance`` tables, builds the
    applicant-level features, saves the parquet output and returns a small
    summary dictionary.
    """
    config = load_bureau_feature_config(feature_config_path)
    bureau_config = config["bureau_features"]
    id_column = bureau_config["id_column"]
    bureau_id_column = bureau_config["bureau_id_column"]
    output_path = bureau_config["output_path"]

    tables = load_raw_tables(
        data_config_path,
        table_names=["bureau", "bureau_balance"],
    )
    bureau = tables["bureau"]
    bureau_balance = tables["bureau_balance"]

    bureau_features = build_bureau_features(
        bureau,
        bureau_balance,
        id_column=id_column,
        bureau_id_column=bureau_id_column,
    )

    save_bureau_features(bureau_features, output_path)

    return {
        "shape": bureau_features.shape,
        "output_path": str(output_path),
        "unique_applicants": int(bureau_features[id_column].nunique()),
        "feature_count": int(bureau_features.shape[1] - 1),
    }
