"""Applicant-level features from non-bureau Home Credit history tables."""

from __future__ import annotations

import gc
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.data.load_raw import load_data_config, resolve_table_paths
from src.features.application_features import safe_divide

DEFAULT_ID_COLUMN = "SK_ID_CURR"
DEFAULT_PREVIOUS_ID_COLUMN = "SK_ID_PREV"
NUMERIC_AGGS = ("mean", "max", "min", "sum", "std")

PREVIOUS_NUMERIC_COLUMNS = (
    "AMT_ANNUITY",
    "AMT_APPLICATION",
    "AMT_CREDIT",
    "AMT_DOWN_PAYMENT",
    "AMT_GOODS_PRICE",
    "HOUR_APPR_PROCESS_START",
    "RATE_DOWN_PAYMENT",
    "CNT_PAYMENT",
    "DAYS_DECISION",
    "DAYS_FIRST_DRAWING",
    "DAYS_FIRST_DUE",
    "DAYS_LAST_DUE",
    "DAYS_TERMINATION",
    "NFLAG_INSURED_ON_APPROVAL",
    "PREV_CREDIT_APPLICATION_RATIO",
    "PREV_DOWN_PAYMENT_CREDIT_RATIO",
    "PREV_ANNUITY_CREDIT_RATIO",
)
PREVIOUS_COLUMNS = (
    DEFAULT_PREVIOUS_ID_COLUMN,
    DEFAULT_ID_COLUMN,
    "NAME_CONTRACT_STATUS",
    *[column for column in PREVIOUS_NUMERIC_COLUMNS if not column.startswith("PREV_")],
)

POS_NUMERIC_COLUMNS = (
    "MONTHS_BALANCE",
    "CNT_INSTALMENT",
    "CNT_INSTALMENT_FUTURE",
    "SK_DPD",
    "SK_DPD_DEF",
    "POS_DPD_FLAG",
    "POS_DPD_DEF_FLAG",
)
POS_COLUMNS = (
    DEFAULT_PREVIOUS_ID_COLUMN,
    DEFAULT_ID_COLUMN,
    "NAME_CONTRACT_STATUS",
    *[column for column in POS_NUMERIC_COLUMNS if not column.startswith("POS_")],
)

INSTALLMENT_NUMERIC_COLUMNS = (
    "NUM_INSTALMENT_VERSION",
    "NUM_INSTALMENT_NUMBER",
    "DAYS_INSTALMENT",
    "DAYS_ENTRY_PAYMENT",
    "AMT_INSTALMENT",
    "AMT_PAYMENT",
    "INSTALLMENT_DAYS_LATE",
    "INSTALLMENT_DAYS_EARLY",
    "INSTALLMENT_PAYMENT_RATIO",
    "INSTALLMENT_PAYMENT_DIFF",
    "INSTALLMENT_LATE_FLAG",
    "INSTALLMENT_UNDERPAID_FLAG",
)
INSTALLMENT_COLUMNS = (
    DEFAULT_PREVIOUS_ID_COLUMN,
    DEFAULT_ID_COLUMN,
    *[column for column in INSTALLMENT_NUMERIC_COLUMNS if not column.startswith("INSTALLMENT_")],
)

CREDIT_CARD_NUMERIC_COLUMNS = (
    "MONTHS_BALANCE",
    "AMT_BALANCE",
    "AMT_CREDIT_LIMIT_ACTUAL",
    "AMT_DRAWINGS_ATM_CURRENT",
    "AMT_DRAWINGS_CURRENT",
    "AMT_DRAWINGS_OTHER_CURRENT",
    "AMT_DRAWINGS_POS_CURRENT",
    "AMT_INST_MIN_REGULARITY",
    "AMT_PAYMENT_CURRENT",
    "AMT_PAYMENT_TOTAL_CURRENT",
    "AMT_RECEIVABLE_PRINCIPAL",
    "AMT_RECIVABLE",
    "AMT_TOTAL_RECEIVABLE",
    "CNT_DRAWINGS_ATM_CURRENT",
    "CNT_DRAWINGS_CURRENT",
    "CNT_DRAWINGS_OTHER_CURRENT",
    "CNT_DRAWINGS_POS_CURRENT",
    "CNT_INSTALMENT_MATURE_CUM",
    "SK_DPD",
    "SK_DPD_DEF",
    "CC_UTILIZATION_RATIO",
    "CC_PAYMENT_BALANCE_RATIO",
    "CC_DPD_FLAG",
    "CC_DPD_DEF_FLAG",
)
CREDIT_CARD_COLUMNS = (
    DEFAULT_PREVIOUS_ID_COLUMN,
    DEFAULT_ID_COLUMN,
    "NAME_CONTRACT_STATUS",
    *[column for column in CREDIT_CARD_NUMERIC_COLUMNS if not column.startswith("CC_")],
)


def _require_columns(frame: pd.DataFrame, table_name: str, columns: set[str]) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{table_name} is missing required columns: {missing}.")
    if frame.empty:
        raise ValueError(f"{table_name} is empty.")


def _numeric_aggregates(
    frame: pd.DataFrame,
    id_column: str,
    columns: tuple[str, ...],
    prefix: str,
) -> pd.DataFrame:
    available = [column for column in columns if column in frame.columns]
    if not available:
        return pd.DataFrame(index=pd.Index([], name=id_column))
    aggregated = frame.groupby(id_column, sort=True)[available].agg(NUMERIC_AGGS)
    flattened_columns: list[str] = []
    for column, stat in aggregated.columns:
        base = column if column.startswith(f"{prefix}_") else f"{prefix}_{column}"
        flattened_columns.append(f"{base}_{stat.upper()}")
    aggregated.columns = flattened_columns
    return aggregated


def _add_category_features(
    features: pd.DataFrame,
    frame: pd.DataFrame,
    id_column: str,
    source_column: str,
    prefix: str,
    categories: tuple[str, ...],
) -> None:
    values = frame[source_column].fillna("__MISSING__").astype(str).str.strip()
    total = features[f"{prefix}_RECORD_COUNT"]
    for category in categories:
        normalized = category.upper().replace(" ", "_")
        count_column = f"{prefix}_{normalized}_COUNT"
        counts = (values == category).astype("int64").groupby(frame[id_column]).sum()
        features[count_column] = counts.reindex(features.index).fillna(0).astype("int64")
        features[f"{prefix}_{normalized}_RATIO"] = safe_divide(features[count_column], total)


def _finalize(features: pd.DataFrame, id_column: str) -> pd.DataFrame:
    output = features.replace([np.inf, -np.inf], np.nan).reset_index()
    columns = sorted(column for column in output.columns if column != id_column)
    return output[[id_column, *columns]].reset_index(drop=True)


def aggregate_previous_applications(
    frame: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    previous_id_column: str = DEFAULT_PREVIOUS_ID_COLUMN,
) -> pd.DataFrame:
    _require_columns(
        frame,
        "previous_application",
        {id_column, previous_id_column, "NAME_CONTRACT_STATUS"},
    )
    data = frame.copy()
    day_columns = [column for column in data.columns if column.startswith("DAYS_")]
    data[day_columns] = data[day_columns].replace(365243, np.nan)
    data["PREV_CREDIT_APPLICATION_RATIO"] = safe_divide(data["AMT_CREDIT"], data["AMT_APPLICATION"])
    data["PREV_DOWN_PAYMENT_CREDIT_RATIO"] = safe_divide(
        data["AMT_DOWN_PAYMENT"], data["AMT_CREDIT"]
    )
    data["PREV_ANNUITY_CREDIT_RATIO"] = safe_divide(data["AMT_ANNUITY"], data["AMT_CREDIT"])
    grouped = data.groupby(id_column, sort=True)
    features = pd.DataFrame(index=grouped.size().index)
    features["PREV_RECORD_COUNT"] = grouped.size().astype("int64")
    features["PREV_CONTRACT_COUNT"] = grouped[previous_id_column].nunique().astype("int64")
    _add_category_features(
        features,
        data,
        id_column,
        "NAME_CONTRACT_STATUS",
        "PREV",
        ("Approved", "Refused", "Canceled", "Unused offer"),
    )
    features = features.join(_numeric_aggregates(data, id_column, PREVIOUS_NUMERIC_COLUMNS, "PREV"))
    return _finalize(features, id_column)


def aggregate_pos_cash(
    frame: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    previous_id_column: str = DEFAULT_PREVIOUS_ID_COLUMN,
) -> pd.DataFrame:
    _require_columns(
        frame,
        "POS_CASH_balance",
        {
            id_column,
            previous_id_column,
            "MONTHS_BALANCE",
            "NAME_CONTRACT_STATUS",
            "SK_DPD",
            "SK_DPD_DEF",
        },
    )
    data = frame.copy()
    data["POS_DPD_FLAG"] = (data["SK_DPD"].fillna(0) > 0).astype("int64")
    data["POS_DPD_DEF_FLAG"] = (data["SK_DPD_DEF"].fillna(0) > 0).astype("int64")
    grouped = data.groupby(id_column, sort=True)
    features = pd.DataFrame(index=grouped.size().index)
    features["POS_RECORD_COUNT"] = grouped.size().astype("int64")
    features["POS_CONTRACT_COUNT"] = grouped[previous_id_column].nunique().astype("int64")
    _add_category_features(
        features,
        data,
        id_column,
        "NAME_CONTRACT_STATUS",
        "POS",
        ("Active", "Completed", "Signed", "Demand"),
    )
    features = features.join(_numeric_aggregates(data, id_column, POS_NUMERIC_COLUMNS, "POS"))
    latest = data.loc[grouped["MONTHS_BALANCE"].idxmax()].set_index(id_column)
    for column in (
        "CNT_INSTALMENT",
        "CNT_INSTALMENT_FUTURE",
        "SK_DPD",
        "SK_DPD_DEF",
    ):
        features[f"POS_LATEST_{column}"] = latest[column].reindex(features.index)
    return _finalize(features, id_column)


def aggregate_installments(
    frame: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    previous_id_column: str = DEFAULT_PREVIOUS_ID_COLUMN,
) -> pd.DataFrame:
    _require_columns(
        frame,
        "installments_payments",
        {
            id_column,
            previous_id_column,
            "DAYS_INSTALMENT",
            "DAYS_ENTRY_PAYMENT",
            "AMT_INSTALMENT",
            "AMT_PAYMENT",
        },
    )
    data = frame.copy()
    day_delta = data["DAYS_ENTRY_PAYMENT"] - data["DAYS_INSTALMENT"]
    data["INSTALLMENT_DAYS_LATE"] = day_delta.clip(lower=0)
    data["INSTALLMENT_DAYS_EARLY"] = (-day_delta).clip(lower=0)
    data["INSTALLMENT_PAYMENT_RATIO"] = safe_divide(data["AMT_PAYMENT"], data["AMT_INSTALMENT"])
    data["INSTALLMENT_PAYMENT_DIFF"] = data["AMT_INSTALMENT"] - data["AMT_PAYMENT"]
    data["INSTALLMENT_LATE_FLAG"] = (day_delta > 0).astype("int64")
    comparable_payment = data["AMT_PAYMENT"].notna() & data["AMT_INSTALMENT"].notna()
    data["INSTALLMENT_UNDERPAID_FLAG"] = (
        comparable_payment & (data["AMT_PAYMENT"] + 1e-6 < data["AMT_INSTALMENT"])
    ).astype("int64")
    grouped = data.groupby(id_column, sort=True)
    features = pd.DataFrame(index=grouped.size().index)
    features["INSTALLMENT_RECORD_COUNT"] = grouped.size().astype("int64")
    features["INSTALLMENT_CONTRACT_COUNT"] = grouped[previous_id_column].nunique().astype("int64")
    features = features.join(
        _numeric_aggregates(
            data,
            id_column,
            INSTALLMENT_NUMERIC_COLUMNS,
            "INSTALLMENT",
        )
    )
    return _finalize(features, id_column)


def aggregate_credit_card(
    frame: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    previous_id_column: str = DEFAULT_PREVIOUS_ID_COLUMN,
) -> pd.DataFrame:
    _require_columns(
        frame,
        "credit_card_balance",
        {
            id_column,
            previous_id_column,
            "MONTHS_BALANCE",
            "AMT_BALANCE",
            "AMT_CREDIT_LIMIT_ACTUAL",
            "NAME_CONTRACT_STATUS",
            "SK_DPD",
            "SK_DPD_DEF",
        },
    )
    data = frame.copy()
    data["CC_UTILIZATION_RATIO"] = safe_divide(data["AMT_BALANCE"], data["AMT_CREDIT_LIMIT_ACTUAL"])
    data["CC_PAYMENT_BALANCE_RATIO"] = safe_divide(
        data["AMT_PAYMENT_TOTAL_CURRENT"], data["AMT_BALANCE"]
    )
    data["CC_DPD_FLAG"] = (data["SK_DPD"].fillna(0) > 0).astype("int64")
    data["CC_DPD_DEF_FLAG"] = (data["SK_DPD_DEF"].fillna(0) > 0).astype("int64")
    grouped = data.groupby(id_column, sort=True)
    features = pd.DataFrame(index=grouped.size().index)
    features["CC_RECORD_COUNT"] = grouped.size().astype("int64")
    features["CC_CONTRACT_COUNT"] = grouped[previous_id_column].nunique().astype("int64")
    _add_category_features(
        features,
        data,
        id_column,
        "NAME_CONTRACT_STATUS",
        "CC",
        ("Active", "Completed", "Signed", "Demand"),
    )
    features = features.join(
        _numeric_aggregates(
            data,
            id_column,
            CREDIT_CARD_NUMERIC_COLUMNS,
            "CC",
        )
    )
    latest = data.loc[grouped["MONTHS_BALANCE"].idxmax()].set_index(id_column)
    for column in (
        "AMT_BALANCE",
        "AMT_CREDIT_LIMIT_ACTUAL",
        "AMT_PAYMENT_TOTAL_CURRENT",
        "SK_DPD",
        "SK_DPD_DEF",
        "CC_UTILIZATION_RATIO",
    ):
        features[f"CC_LATEST_{column}"] = latest[column].reindex(features.index)
    return _finalize(features, id_column)


def merge_advanced_history_features(
    feature_tables: list[pd.DataFrame],
    id_column: str = DEFAULT_ID_COLUMN,
) -> pd.DataFrame:
    if not feature_tables:
        raise ValueError("At least one advanced history feature table is required.")
    result = feature_tables[0]
    for index, table in enumerate(feature_tables):
        if id_column not in table.columns:
            raise ValueError(f"Advanced feature table {index} is missing '{id_column}'.")
        if table[id_column].duplicated().any():
            raise ValueError(f"Advanced feature table {index} has duplicate '{id_column}'.")
        if index > 0:
            result = result.merge(
                table,
                on=id_column,
                how="outer",
                validate="one_to_one",
            )
    columns = sorted(column for column in result.columns if column != id_column)
    return result[[id_column, *columns]].replace([np.inf, -np.inf], np.nan)


def _load_selected_columns(
    data_config_path: str | Path,
    table_name: str,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    config = load_data_config(data_config_path)
    paths = resolve_table_paths(config)
    if table_name not in paths:
        raise ValueError(f"Data config is missing table '{table_name}'.")
    return pd.read_csv(paths[table_name], usecols=list(dict.fromkeys(columns)))


def load_advanced_history_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Feature config not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    section = config.get("advanced_history_features") if isinstance(config, dict) else None
    if not isinstance(section, dict):
        raise ValueError("Feature config must contain 'advanced_history_features'.")
    for key in ("id_column", "previous_id_column", "output_path"):
        if key not in section:
            raise ValueError(f"advanced_history_features is missing '{key}'.")
    return section


def run_build_advanced_history_features(
    data_config_path: str | Path = "configs/data.yaml",
    feature_config_path: str | Path = "configs/features.yaml",
) -> dict[str, Any]:
    config = load_advanced_history_config(feature_config_path)
    id_column = str(config["id_column"])
    previous_id_column = str(config["previous_id_column"])
    specifications: tuple[
        tuple[
            str,
            tuple[str, ...],
            Callable[[pd.DataFrame, str, str], pd.DataFrame],
        ],
        ...,
    ] = (
        ("previous_application", PREVIOUS_COLUMNS, aggregate_previous_applications),
        ("pos_cash_balance", POS_COLUMNS, aggregate_pos_cash),
        ("installments_payments", INSTALLMENT_COLUMNS, aggregate_installments),
        ("credit_card_balance", CREDIT_CARD_COLUMNS, aggregate_credit_card),
    )

    feature_tables: list[pd.DataFrame] = []
    source_rows: dict[str, int] = {}
    for table_name, columns, aggregator in specifications:
        raw = _load_selected_columns(data_config_path, table_name, columns)
        source_rows[table_name] = int(len(raw))
        feature_tables.append(aggregator(raw, id_column, previous_id_column))
        del raw
        gc.collect()

    features = merge_advanced_history_features(feature_tables, id_column)
    output_path = Path(config["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output_path, index=False)
    return {
        "shape": features.shape,
        "unique_applicants": int(features[id_column].nunique()),
        "feature_count": int(features.shape[1] - 1),
        "source_rows": source_rows,
        "output_path": str(output_path),
    }
