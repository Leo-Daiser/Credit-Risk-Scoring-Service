import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import src.features.bureau_features as bureau_features
from src.features.bureau_features import (
    aggregate_bureau_balance,
    aggregate_bureau_to_applicant,
    build_bureau_features,
    merge_bureau_with_balance_features,
    run_build_bureau_features,
    save_bureau_features,
)


# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------
def _build_bureau_balance() -> pd.DataFrame:
    """bureau_balance with multiple rows per SK_ID_BUREAU."""
    rows = [
        # SK_ID_BUREAU == 10: 6 months, statuses 0,0,1,C,X,5
        (10, -1, "0"),
        (10, -2, "0"),
        (10, -3, "1"),
        (10, -4, "C"),
        (10, -5, "X"),
        (10, -6, "5"),
        # SK_ID_BUREAU == 11: 2 months, all "C"
        (11, -1, "C"),
        (11, -2, "C"),
    ]
    return pd.DataFrame(rows, columns=["SK_ID_BUREAU", "MONTHS_BALANCE", "STATUS"])


def _build_bureau() -> pd.DataFrame:
    """bureau with three loans across two applicants."""
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1, 2],
            "SK_ID_BUREAU": [10, 11, 12],
            "CREDIT_ACTIVE": ["Active", "Closed", "Active"],
            "CREDIT_TYPE": ["Consumer credit", "Credit card", "Car loan"],
            "DAYS_CREDIT": [-100, -200, -50],
            "CREDIT_DAY_OVERDUE": [0, 5, 0],
            "AMT_CREDIT_SUM": [1000.0, 2000.0, 500.0],
            "AMT_CREDIT_SUM_DEBT": [100.0, 500.0, 0.0],
            "AMT_CREDIT_SUM_OVERDUE": [0.0, 50.0, 0.0],
        }
    )


def _build_bureau_enriched() -> pd.DataFrame:
    """bureau already enriched with bureau_balance loan-level features."""
    df = _build_bureau().copy()
    df["BUREAU_BALANCE_DPD_COUNT"] = [1, 0, 2]
    df["BUREAU_BALANCE_DPD_RATIO"] = [0.5, 0.0, 0.4]
    df["BUREAU_BALANCE_BAD_DEBT_RATIO"] = [0.0, 0.0, 0.2]
    return df


# ---------------------------------------------------------------------------
# aggregate_bureau_balance
# ---------------------------------------------------------------------------
def test_aggregate_bureau_balance_one_row_per_bureau_id() -> None:
    out = aggregate_bureau_balance(_build_bureau_balance())

    assert out["SK_ID_BUREAU"].is_unique
    assert set(out["SK_ID_BUREAU"]) == {10, 11}
    assert len(out) == 2


def test_aggregate_bureau_balance_status_counts_and_ratios() -> None:
    out = aggregate_bureau_balance(_build_bureau_balance()).set_index("SK_ID_BUREAU")

    row = out.loc[10]
    assert row["BUREAU_BALANCE_MONTHS_COUNT"] == 6
    assert row["BUREAU_BALANCE_STATUS_0_COUNT"] == 2
    assert row["BUREAU_BALANCE_STATUS_1_COUNT"] == 1
    assert row["BUREAU_BALANCE_STATUS_5_COUNT"] == 1
    assert row["BUREAU_BALANCE_STATUS_C_COUNT"] == 1
    assert row["BUREAU_BALANCE_STATUS_X_COUNT"] == 1

    assert row["BUREAU_BALANCE_STATUS_0_RATIO"] == pytest.approx(2 / 6)
    assert row["BUREAU_BALANCE_STATUS_1_RATIO"] == pytest.approx(1 / 6)
    assert row["BUREAU_BALANCE_STATUS_C_RATIO"] == pytest.approx(1 / 6)
    assert row["BUREAU_BALANCE_STATUS_X_RATIO"] == pytest.approx(1 / 6)

    # Statuses that never appear must still produce zero columns.
    assert row["BUREAU_BALANCE_STATUS_2_COUNT"] == 0
    assert row["BUREAU_BALANCE_STATUS_2_RATIO"] == 0.0


def test_aggregate_bureau_balance_dpd_features() -> None:
    out = aggregate_bureau_balance(_build_bureau_balance()).set_index("SK_ID_BUREAU")

    row = out.loc[10]
    # DPD = statuses 1/2/3/4/5 -> here status "1" and status "5".
    assert row["BUREAU_BALANCE_DPD_COUNT"] == 2
    assert row["BUREAU_BALANCE_DPD_RATIO"] == pytest.approx(2 / 6)
    # Bad debt = status "5".
    assert row["BUREAU_BALANCE_BAD_DEBT_COUNT"] == 1
    assert row["BUREAU_BALANCE_BAD_DEBT_RATIO"] == pytest.approx(1 / 6)

    closed = out.loc[11]
    assert closed["BUREAU_BALANCE_DPD_COUNT"] == 0
    assert closed["BUREAU_BALANCE_DPD_RATIO"] == 0.0
    assert closed["BUREAU_BALANCE_BAD_DEBT_COUNT"] == 0


# ---------------------------------------------------------------------------
# merge_bureau_with_balance_features
# ---------------------------------------------------------------------------
def test_merge_bureau_with_balance_features_preserves_bureau_row_count() -> None:
    bureau = _build_bureau()
    balance_features = aggregate_bureau_balance(_build_bureau_balance())

    merged = merge_bureau_with_balance_features(bureau, balance_features)

    # Row count preserved (loan 12 has no balance history).
    assert len(merged) == len(bureau)
    assert merged["SK_ID_BUREAU"].tolist() == bureau["SK_ID_BUREAU"].tolist()

    # Missing balance count/ratio columns are filled with 0.
    loan_12 = merged.loc[merged["SK_ID_BUREAU"] == 12].iloc[0]
    assert loan_12["BUREAU_BALANCE_MONTHS_COUNT"] == 0
    assert loan_12["BUREAU_BALANCE_DPD_RATIO"] == 0.0


# ---------------------------------------------------------------------------
# aggregate_bureau_to_applicant
# ---------------------------------------------------------------------------
def test_aggregate_bureau_to_applicant_one_row_per_applicant() -> None:
    out = aggregate_bureau_to_applicant(_build_bureau_enriched())

    assert out["SK_ID_CURR"].is_unique
    assert set(out["SK_ID_CURR"]) == {1, 2}
    assert out.columns[0] == "SK_ID_CURR"


def test_aggregate_bureau_to_applicant_basic_counts() -> None:
    out = aggregate_bureau_to_applicant(_build_bureau_enriched()).set_index(
        "SK_ID_CURR"
    )

    applicant_1 = out.loc[1]
    assert applicant_1["BUREAU_LOAN_COUNT"] == 2
    assert applicant_1["BUREAU_ACTIVE_LOAN_COUNT"] == 1
    assert applicant_1["BUREAU_CLOSED_LOAN_COUNT"] == 1
    assert applicant_1["BUREAU_ACTIVE_LOAN_RATIO"] == pytest.approx(0.5)
    assert applicant_1["BUREAU_CLOSED_LOAN_RATIO"] == pytest.approx(0.5)

    applicant_2 = out.loc[2]
    assert applicant_2["BUREAU_LOAN_COUNT"] == 1
    assert applicant_2["BUREAU_ACTIVE_LOAN_COUNT"] == 1
    assert applicant_2["BUREAU_ACTIVE_LOAN_RATIO"] == pytest.approx(1.0)
    assert applicant_2["BUREAU_CLOSED_LOAN_RATIO"] == pytest.approx(0.0)


def test_aggregate_bureau_to_applicant_numeric_aggregations() -> None:
    out = aggregate_bureau_to_applicant(_build_bureau_enriched()).set_index(
        "SK_ID_CURR"
    )

    applicant_1 = out.loc[1]
    assert applicant_1["BUREAU_AMT_CREDIT_SUM_MEAN"] == pytest.approx(1500.0)
    assert applicant_1["BUREAU_AMT_CREDIT_SUM_SUM"] == pytest.approx(3000.0)
    assert applicant_1["BUREAU_AMT_CREDIT_SUM_MAX"] == pytest.approx(2000.0)
    assert applicant_1["BUREAU_AMT_CREDIT_SUM_MIN"] == pytest.approx(1000.0)

    assert applicant_1["BUREAU_AMT_CREDIT_SUM_DEBT_MEAN"] == pytest.approx(300.0)
    assert applicant_1["BUREAU_AMT_CREDIT_SUM_DEBT_SUM"] == pytest.approx(600.0)
    assert applicant_1["BUREAU_AMT_CREDIT_SUM_DEBT_MAX"] == pytest.approx(500.0)
    assert applicant_1["BUREAU_AMT_CREDIT_SUM_DEBT_MIN"] == pytest.approx(100.0)


def test_aggregate_bureau_to_applicant_debt_ratios() -> None:
    out = aggregate_bureau_to_applicant(_build_bureau_enriched()).set_index(
        "SK_ID_CURR"
    )

    applicant_1 = out.loc[1]
    # total debt 600 / total credit 3000 = 0.2
    assert applicant_1["BUREAU_DEBT_CREDIT_RATIO"] == pytest.approx(0.2)
    # loan 11 is overdue (CREDIT_DAY_OVERDUE=5, AMT_CREDIT_SUM_OVERDUE=50)
    assert applicant_1["BUREAU_HAS_OVERDUE_FLAG"] == 1
    assert applicant_1["BUREAU_OVERDUE_LOAN_COUNT"] == 1
    assert applicant_1["BUREAU_OVERDUE_LOAN_RATIO"] == pytest.approx(0.5)

    applicant_2 = out.loc[2]
    # no debt -> safe division yields 0 / 500 == 0.0; no overdue loans.
    assert applicant_2["BUREAU_DEBT_CREDIT_RATIO"] == pytest.approx(0.0)
    assert applicant_2["BUREAU_HAS_OVERDUE_FLAG"] == 0
    assert applicant_2["BUREAU_OVERDUE_LOAN_COUNT"] == 0
    assert applicant_2["BUREAU_OVERDUE_LOAN_RATIO"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# build_bureau_features (full mini pipeline)
# ---------------------------------------------------------------------------
def test_build_bureau_features_contract() -> None:
    bureau = _build_bureau()
    bureau_balance = _build_bureau_balance()

    out = build_bureau_features(bureau, bureau_balance)

    # SK_ID_CURR is the first column and unique.
    assert out.columns[0] == "SK_ID_CURR"
    assert out["SK_ID_CURR"].is_unique
    assert set(out["SK_ID_CURR"]) == {1, 2}

    expected_columns = {
        "BUREAU_LOAN_COUNT",
        "BUREAU_ACTIVE_LOAN_COUNT",
        "BUREAU_CLOSED_LOAN_COUNT",
        "BUREAU_DEBT_CREDIT_RATIO",
        "BUREAU_HAS_OVERDUE_FLAG",
        "BUREAU_CREDIT_TYPE_CONSUMER_CREDIT_COUNT",
        "BUREAU_AMT_CREDIT_SUM_SUM",
        # bureau_balance roll-up features must be present too.
        "BUREAU_BALANCE_DPD_COUNT_SUM",
        "BUREAU_BALANCE_DPD_RATIO_MEAN",
    }
    assert expected_columns.issubset(set(out.columns))

    # No infinities anywhere.
    numeric = out.select_dtypes(include="number")
    assert not np.isinf(numeric.to_numpy()).any()

    # Feature columns are deterministically sorted after SK_ID_CURR.
    feature_cols = list(out.columns[1:])
    assert feature_cols == sorted(feature_cols)


# ---------------------------------------------------------------------------
# save_bureau_features
# ---------------------------------------------------------------------------
def test_save_bureau_features_creates_parquet(tmp_path: Path) -> None:
    bureau_features_df = build_bureau_features(_build_bureau(), _build_bureau_balance())

    output_path = tmp_path / "processed" / "bureau_features.parquet"
    save_bureau_features(bureau_features_df, output_path)

    assert output_path.exists()

    reloaded = pd.read_parquet(output_path)
    assert reloaded.shape == bureau_features_df.shape
    assert list(reloaded.columns) == list(bureau_features_df.columns)
    assert reloaded.columns[0] == "SK_ID_CURR"


# ---------------------------------------------------------------------------
# run_build_bureau_features
# ---------------------------------------------------------------------------
def test_run_build_bureau_features_uses_selected_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_load_raw_tables(config_path, table_names=None):
        captured["config_path"] = config_path
        captured["table_names"] = table_names
        return {
            "bureau": _build_bureau(),
            "bureau_balance": _build_bureau_balance(),
        }

    saved: dict[str, object] = {}

    def fake_save_bureau_features(df, output_path):
        saved["shape"] = df.shape
        saved["output_path"] = output_path

    monkeypatch.setattr(bureau_features, "load_raw_tables", fake_load_raw_tables)
    monkeypatch.setattr(
        bureau_features, "save_bureau_features", fake_save_bureau_features
    )

    summary = run_build_bureau_features()

    # Only bureau and bureau_balance must be requested.
    assert captured["table_names"] == ["bureau", "bureau_balance"]

    assert summary["unique_applicants"] == 2
    assert summary["shape"][0] == 2
    assert summary["feature_count"] == summary["shape"][1] - 1
    assert summary["output_path"].endswith("bureau_features.parquet")
    assert saved["shape"][0] == 2
