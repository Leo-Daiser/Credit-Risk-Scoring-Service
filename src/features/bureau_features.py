"""Bureau / bureau balance historical aggregation layer (Phase 2.2).

This module builds applicant-level historical credit-bureau features from the
Home Credit Default Risk ``bureau`` and ``bureau_balance`` tables. The output
is keyed by ``SK_ID_CURR`` so it can be merged directly into the
application-level feature table produced in Phase 2.1.

Pipeline overview:

1. ``aggregate_bureau_balance`` collapses ``bureau_balance`` (one row per
   ``SK_ID_BUREAU`` / month) into one row per ``SK_ID_BUREAU`` with monthly
   status counts, DPD (days-past-due) signals and tenure information.
2. ``merge_bureau_with_balance`` left-joins those per-credit balance features
   onto ``bureau`` (preserving every bureau row); credits without any balance
   history get balance counts filled with ``0``.
3. ``aggregate_bureau_to_applicant`` collapses the enriched ``bureau`` table
   into one row per ``SK_ID_CURR`` with numeric aggregations, categorical
   counts (``CREDIT_ACTIVE`` / ``CREDIT_TYPE``) and a handful of safe ratios.

No model training, encoding, scaling or imputation happens here — this is a
pure, deterministic feature-engineering layer. The contract is:

- exactly one row per applicant that appears in ``bureau``;
- ``SK_ID_CURR`` is the first column, followed by deterministically sorted
  feature columns;
- ``SK_ID_BUREAU`` never leaks into the applicant-level output.
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

# bureau_balance.STATUS values that represent a number of days past due.
# ``C`` = closed, ``X`` = unknown/no information; the digits are DPD buckets.
DPD_STATUS_VALUES = ["1", "2", "3", "4", "5"]
NON_DPD_STATUS_VALUES = ["0", "C", "X"]
ALL_STATUS_VALUES = ["0", "1", "2", "3", "4", "5", "C", "X"]

# Numeric bureau columns and the aggregations applied per applicant. Only
# columns that are actually present in the input are used, so the layer never
# fails on a partial schema.
BUREAU_NUMERIC_AGGREGATIONS: dict[str, list[str]] = {
    "DAYS_CREDIT": ["min", "max", "mean"],
    "CREDIT_DAY_OVERDUE": ["max", "mean"],
    "DAYS_CREDIT_ENDDATE": ["min", "max", "mean"],
    "DAYS_ENDDATE_FACT": ["min", "max", "mean"],
    "AMT_CREDIT_MAX_OVERDUE": ["max", "mean"],
    "CNT_CREDIT_PROLONG": ["sum", "max"],
    "AMT_CREDIT_SUM": ["sum", "mean", "max"],
    "AMT_CREDIT_SUM_DEBT": ["sum", "mean", "max"],
    "AMT_CREDIT_SUM_LIMIT": ["sum", "mean"],
    "AMT_CREDIT_SUM_OVERDUE": ["sum", "max", "mean"],
    "DAYS_CREDIT_UPDATE": ["min", "max", "mean"],
    "AMT_ANNUITY": ["sum", "mean", "max"],
}

# Per-credit balance features (output of ``aggregate_bureau_balance``) and how
# they roll up to the applicant level.
BUREAU_BALANCE_ROLLUP_AGGREGATIONS: dict[str, list[str]] = {
    "BB_MONTHS_COUNT": ["sum", "mean", "max"],
    "BB_DPD_MONTHS_COUNT": ["sum", "mean", "max"],
    "BB_DPD_RATIO": ["mean", "max"],
    "BB_MAX_DPD_STATUS": ["max", "mean"],
}


def load_bureau_feature_config(config_path: str | Path) -> dict[str, Any]:
    """Load and validate the bureau feature-engineering configuration.

    Reads the ``bureau_features`` section from ``configs/features.yaml`` and
    returns it with defaults applied. Raises a clear error if the section or
    its required output path is missing.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Feature config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("Feature config must be a dictionary.")

    bureau_config = config.get("bureau_features")
    if not isinstance(bureau_config, dict):
        raise ValueError("Feature config must contain a 'bureau_features' dictionary.")

    if "output_path" not in bureau_config:
        raise ValueError("Feature config 'bureau_features' must contain 'output_path'.")

    bureau_config.setdefault("id_column", DEFAULT_ID_COLUMN)
    bureau_config.setdefault("bureau_id_column", DEFAULT_BUREAU_ID_COLUMN)

    return bureau_config


def aggregate_bureau_balance(
    bureau_balance: pd.DataFrame,
    bureau_id_column: str = DEFAULT_BUREAU_ID_COLUMN,
) -> pd.DataFrame:
    """Collapse ``bureau_balance`` into one row per ``SK_ID_BUREAU``.

    Produces, per bureau credit:

    - ``BB_MONTHS_COUNT``: number of monthly records;
    - ``BB_MONTHS_BALANCE_MIN`` / ``BB_MONTHS_BALANCE_MAX``: tenure span
      (months are negative offsets from the application date);
    - ``BB_STATUS_<S>_COUNT`` for every possible status value;
    - ``BB_DPD_MONTHS_COUNT``: months in any days-past-due bucket (1..5);
    - ``BB_DPD_RATIO``: share of months in a DPD bucket;
    - ``BB_MAX_DPD_STATUS``: worst DPD bucket reached (0 if none).

    The output column order is deterministic: the id column first, then
    sorted feature columns. An empty input yields an empty, correctly-typed
    frame.
    """
    if bureau_id_column not in bureau_balance.columns:
        raise ValueError(
            f"bureau_balance is missing the id column '{bureau_id_column}'."
        )
    if "STATUS" not in bureau_balance.columns:
        raise ValueError("bureau_balance is missing the 'STATUS' column.")

    feature_columns = (
        ["BB_MONTHS_COUNT", "BB_MONTHS_BALANCE_MIN", "BB_MONTHS_BALANCE_MAX"]
        + [f"BB_STATUS_{status}_COUNT" for status in ALL_STATUS_VALUES]
        + ["BB_DPD_MONTHS_COUNT", "BB_DPD_RATIO", "BB_MAX_DPD_STATUS"]
    )

    if bureau_balance.empty:
        empty = pd.DataFrame(columns=[bureau_id_column, *feature_columns])
        return empty

    df = bureau_balance.copy()
    df["STATUS"] = df["STATUS"].astype("string").str.strip()

    grouped = df.groupby(bureau_id_column, sort=True)

    result = pd.DataFrame(index=grouped.size().index)
    result["BB_MONTHS_COUNT"] = grouped.size()

    if "MONTHS_BALANCE" in df.columns:
        result["BB_MONTHS_BALANCE_MIN"] = grouped["MONTHS_BALANCE"].min()
        result["BB_MONTHS_BALANCE_MAX"] = grouped["MONTHS_BALANCE"].max()
    else:
        result["BB_MONTHS_BALANCE_MIN"] = np.nan
        result["BB_MONTHS_BALANCE_MAX"] = np.nan

    # Per-status month counts. crosstab guarantees one column per observed
    # status; we reindex to the full, fixed status vocabulary so the contract
    # is stable regardless of which statuses appear in the data.
    status_counts = pd.crosstab(df[bureau_id_column], df["STATUS"])
    status_counts = status_counts.reindex(columns=ALL_STATUS_VALUES, fill_value=0)
    for status in ALL_STATUS_VALUES:
        result[f"BB_STATUS_{status}_COUNT"] = status_counts[status]

    dpd_columns = [f"BB_STATUS_{status}_COUNT" for status in DPD_STATUS_VALUES]
    result["BB_DPD_MONTHS_COUNT"] = result[dpd_columns].sum(axis=1)
    result["BB_DPD_RATIO"] = safe_divide(
        result["BB_DPD_MONTHS_COUNT"], result["BB_MONTHS_COUNT"]
    )

    # Worst DPD bucket reached (0 when the credit was never past due).
    dpd_numeric = df[df["STATUS"].isin(DPD_STATUS_VALUES)].copy()
    if not dpd_numeric.empty:
        dpd_numeric["STATUS_NUM"] = dpd_numeric["STATUS"].astype("int64")
        max_dpd = dpd_numeric.groupby(bureau_id_column)["STATUS_NUM"].max()
    else:
        max_dpd = pd.Series(dtype="int64")
    result["BB_MAX_DPD_STATUS"] = (
        max_dpd.reindex(result.index).fillna(0).astype("int64")
    )

    result = result.reset_index().rename(columns={"index": bureau_id_column})
    if bureau_id_column not in result.columns:
        result = result.rename(columns={result.columns[0]: bureau_id_column})

    ordered = [bureau_id_column, *sorted(feature_columns)]
    return result[ordered]


def merge_bureau_with_balance(
    bureau: pd.DataFrame,
    bureau_balance_features: pd.DataFrame,
    bureau_id_column: str = DEFAULT_BUREAU_ID_COLUMN,
) -> pd.DataFrame:
    """Left-join per-credit balance features onto the ``bureau`` table.

    Every ``bureau`` row is preserved. Credits without any balance history
    get count-style balance columns filled with ``0``; ratio/level columns
    are left as ``NaN`` (there is genuinely no DPD ratio without history).
    """
    if bureau_id_column not in bureau.columns:
        raise ValueError(f"bureau is missing the id column '{bureau_id_column}'.")

    merged = bureau.merge(bureau_balance_features, on=bureau_id_column, how="left")

    count_columns = [
        col
        for col in bureau_balance_features.columns
        if col != bureau_id_column and col.endswith("_COUNT")
    ]
    for col in count_columns:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    return merged


def _categorical_counts(
    df: pd.DataFrame,
    id_column: str,
    category_column: str,
    prefix: str,
) -> pd.DataFrame:
    """One row per id with a ``<prefix>_<VALUE>_COUNT`` column per category.

    Category values are slugified (uppercased, non-alphanumeric replaced with
    underscores) and the resulting columns are sorted deterministically.
    """
    values = df[category_column].astype("string").str.strip()
    slugs = (
        values.str.upper().str.replace(r"[^0-9A-Z]+", "_", regex=True).str.strip("_")
    )
    work = pd.DataFrame({id_column: df[id_column], "_slug": slugs})
    counts = pd.crosstab(work[id_column], work["_slug"])
    counts.columns = [f"{prefix}_{slug}_COUNT" for slug in counts.columns]
    counts = counts.reindex(sorted(counts.columns), axis=1)
    return counts


def aggregate_bureau_to_applicant(
    bureau: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    bureau_id_column: str = DEFAULT_BUREAU_ID_COLUMN,
) -> pd.DataFrame:
    """Collapse the (balance-enriched) ``bureau`` table to one row per applicant.

    Builds:

    - ``BUREAU_COUNT``: number of bureau credits for the applicant;
    - ``BUREAU_<COL>_<AGG>`` numeric aggregations for known bureau columns;
    - ``BUREAU_BB_<COL>_<AGG>`` rollups of the per-credit balance features;
    - ``BUREAU_CREDIT_ACTIVE_<VALUE>_COUNT`` and
      ``BUREAU_CREDIT_TYPE_NUNIQUE`` categorical signals;
    - safe ratios (``BUREAU_ACTIVE_CREDIT_RATIO``,
      ``BUREAU_DEBT_CREDIT_RATIO``, ``BUREAU_OVERDUE_DEBT_RATIO``).
    """
    if id_column not in bureau.columns:
        raise ValueError(f"bureau is missing the id column '{id_column}'.")

    grouped = bureau.groupby(id_column, sort=True)

    result = pd.DataFrame(index=grouped.size().index)
    result["BUREAU_COUNT"] = grouped.size()

    if bureau_id_column in bureau.columns:
        result["BUREAU_CREDIT_NUNIQUE"] = grouped[bureau_id_column].nunique()

    # Numeric aggregations for whichever known columns are present.
    for column, aggregations in BUREAU_NUMERIC_AGGREGATIONS.items():
        if column not in bureau.columns:
            continue
        agg_result = grouped[column].agg(aggregations)
        for aggregation in aggregations:
            result[f"BUREAU_{column}_{aggregation.upper()}"] = agg_result[aggregation]

    # Rollups of the per-credit bureau_balance features.
    for column, aggregations in BUREAU_BALANCE_ROLLUP_AGGREGATIONS.items():
        if column not in bureau.columns:
            continue
        agg_result = grouped[column].agg(aggregations)
        for aggregation in aggregations:
            result[f"BUREAU_{column}_{aggregation.upper()}"] = agg_result[aggregation]

    # Status-count rollups (sum of monthly status counts across all credits).
    status_count_columns = [f"BB_STATUS_{status}_COUNT" for status in ALL_STATUS_VALUES]
    for column in status_count_columns:
        if column in bureau.columns:
            result[f"BUREAU_{column}_SUM"] = grouped[column].sum()

    # Categorical: CREDIT_ACTIVE counts + CREDIT_TYPE diversity.
    if "CREDIT_ACTIVE" in bureau.columns:
        active_counts = _categorical_counts(
            bureau, id_column, "CREDIT_ACTIVE", "BUREAU_CREDIT_ACTIVE"
        )
        result = result.join(active_counts, how="left")
        active_count_cols = list(active_counts.columns)
        result[active_count_cols] = result[active_count_cols].fillna(0)

    if "CREDIT_TYPE" in bureau.columns:
        result["BUREAU_CREDIT_TYPE_NUNIQUE"] = grouped["CREDIT_TYPE"].nunique()

    # Safe ratios derived from the aggregates above.
    active_col = "BUREAU_CREDIT_ACTIVE_ACTIVE_COUNT"
    if active_col in result.columns:
        result["BUREAU_ACTIVE_CREDIT_RATIO"] = safe_divide(
            result[active_col], result["BUREAU_COUNT"]
        )

    if {"BUREAU_AMT_CREDIT_SUM_DEBT_SUM", "BUREAU_AMT_CREDIT_SUM_SUM"} <= set(
        result.columns
    ):
        result["BUREAU_DEBT_CREDIT_RATIO"] = safe_divide(
            result["BUREAU_AMT_CREDIT_SUM_DEBT_SUM"],
            result["BUREAU_AMT_CREDIT_SUM_SUM"],
        )

    if {
        "BUREAU_AMT_CREDIT_SUM_OVERDUE_SUM",
        "BUREAU_AMT_CREDIT_SUM_DEBT_SUM",
    } <= set(result.columns):
        result["BUREAU_OVERDUE_DEBT_RATIO"] = safe_divide(
            result["BUREAU_AMT_CREDIT_SUM_OVERDUE_SUM"],
            result["BUREAU_AMT_CREDIT_SUM_DEBT_SUM"],
        )

    result = result.replace([np.inf, -np.inf], np.nan)

    result = result.reset_index().rename(columns={"index": id_column})
    if id_column not in result.columns:
        result = result.rename(columns={result.columns[0]: id_column})

    feature_columns = sorted(col for col in result.columns if col != id_column)
    return result[[id_column, *feature_columns]]


def build_bureau_features(
    bureau: pd.DataFrame,
    bureau_balance: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    bureau_id_column: str = DEFAULT_BUREAU_ID_COLUMN,
) -> pd.DataFrame:
    """Build the applicant-level bureau feature table.

    The output has exactly one row per ``SK_ID_CURR`` present in ``bureau``,
    with ``SK_ID_CURR`` as the first column followed by deterministically
    sorted feature columns. It is designed to be left-merged into the
    application-level features by ``SK_ID_CURR``.

    Raises:
        ValueError: if ``bureau`` is missing ``id_column`` or
            ``bureau_id_column``, or if ``bureau_balance`` is missing
            ``bureau_id_column``.
    """
    if id_column not in bureau.columns:
        raise ValueError(f"bureau is missing the applicant id column '{id_column}'.")
    if bureau_id_column not in bureau.columns:
        raise ValueError(
            f"bureau is missing the bureau id column '{bureau_id_column}'."
        )
    if bureau_id_column not in bureau_balance.columns:
        raise ValueError(
            f"bureau_balance is missing the bureau id column " f"'{bureau_id_column}'."
        )

    balance_features = aggregate_bureau_balance(
        bureau_balance, bureau_id_column=bureau_id_column
    )
    enriched = merge_bureau_with_balance(
        bureau, balance_features, bureau_id_column=bureau_id_column
    )
    applicant_features = aggregate_bureau_to_applicant(
        enriched, id_column=id_column, bureau_id_column=bureau_id_column
    )

    return applicant_features


def save_bureau_features(
    bureau_features: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Persist the applicant-level bureau feature table as a parquet file.

    Parent directories are created if they do not exist.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bureau_features.to_parquet(output_path, index=False)
    return output_path


def run_build_bureau_features(
    data_config_path: str | Path = "configs/data.yaml",
    feature_config_path: str | Path = "configs/features.yaml",
) -> dict[str, Any]:
    """End-to-end entrypoint used by the CLI.

    Loads only the ``bureau`` and ``bureau_balance`` tables, builds the
    applicant-level bureau features, saves the parquet output and returns a
    small summary dictionary.
    """
    bureau_config = load_bureau_feature_config(feature_config_path)

    tables = load_raw_tables(
        data_config_path,
        table_names=["bureau", "bureau_balance"],
    )
    bureau = tables["bureau"]
    bureau_balance = tables["bureau_balance"]

    bureau_features = build_bureau_features(
        bureau,
        bureau_balance,
        id_column=bureau_config["id_column"],
        bureau_id_column=bureau_config["bureau_id_column"],
    )

    output_path = save_bureau_features(bureau_features, bureau_config["output_path"])

    return {
        "bureau_features_shape": bureau_features.shape,
        "bureau_features_path": str(output_path),
        "n_applicants": int(bureau_features.shape[0]),
        "n_feature_columns": int(bureau_features.shape[1] - 1),
    }
