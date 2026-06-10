import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features.bureau_features import (
    aggregate_bureau_balance,
    aggregate_bureau_to_applicant,
    build_bureau_features,
    load_bureau_feature_config,
    merge_bureau_with_balance,
    save_bureau_features,
)


def _build_bureau() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [100001, 100001, 100002, 100003],
            "SK_ID_BUREAU": [1, 2, 3, 4],
            "CREDIT_ACTIVE": ["Active", "Closed", "Active", "Bad debt"],
            "CREDIT_TYPE": [
                "Consumer credit",
                "Credit card",
                "Consumer credit",
                "Car loan",
            ],
            "DAYS_CREDIT": [-500, -1000, -200, -50],
            "CREDIT_DAY_OVERDUE": [0, 0, 5, 30],
            "AMT_CREDIT_SUM": [100000.0, 50000.0, 200000.0, 0.0],
            "AMT_CREDIT_SUM_DEBT": [40000.0, 0.0, 150000.0, 0.0],
            "AMT_CREDIT_SUM_OVERDUE": [0.0, 0.0, 1000.0, 0.0],
            "CNT_CREDIT_PROLONG": [0, 1, 0, 0],
        }
    )


def _build_bureau_balance() -> pd.DataFrame:
    # Credit 1: 3 months, one DPD (status "1"); credit 2: 2 closed months;
    # credit 3: 1 month with status "2"; credit 4 has NO balance history.
    return pd.DataFrame(
        {
            "SK_ID_BUREAU": [1, 1, 1, 2, 2, 3],
            "MONTHS_BALANCE": [0, -1, -2, 0, -1, 0],
            "STATUS": ["0", "1", "C", "C", "C", "2"],
        }
    )


# ---------------------------------------------------------------------------
# aggregate_bureau_balance
# ---------------------------------------------------------------------------
def test_aggregate_bureau_balance_basic_counts() -> None:
    bb = _build_bureau_balance()

    out = aggregate_bureau_balance(bb)

    assert out.columns[0] == "SK_ID_BUREAU"
    # One row per distinct SK_ID_BUREAU present in balance.
    assert sorted(out["SK_ID_BUREAU"].tolist()) == [1, 2, 3]

    row1 = out.loc[out["SK_ID_BUREAU"] == 1].iloc[0]
    assert row1["BB_MONTHS_COUNT"] == 3
    assert row1["BB_STATUS_0_COUNT"] == 1
    assert row1["BB_STATUS_1_COUNT"] == 1
    assert row1["BB_STATUS_C_COUNT"] == 1
    assert row1["BB_DPD_MONTHS_COUNT"] == 1
    assert row1["BB_DPD_RATIO"] == pytest.approx(1 / 3)
    assert row1["BB_MAX_DPD_STATUS"] == 1
    assert row1["BB_MONTHS_BALANCE_MIN"] == -2
    assert row1["BB_MONTHS_BALANCE_MAX"] == 0


def test_aggregate_bureau_balance_no_dpd() -> None:
    bb = _build_bureau_balance()

    out = aggregate_bureau_balance(bb)

    row2 = out.loc[out["SK_ID_BUREAU"] == 2].iloc[0]
    assert row2["BB_MONTHS_COUNT"] == 2
    assert row2["BB_DPD_MONTHS_COUNT"] == 0
    assert row2["BB_DPD_RATIO"] == 0.0
    assert row2["BB_MAX_DPD_STATUS"] == 0


def test_aggregate_bureau_balance_columns_sorted() -> None:
    bb = _build_bureau_balance()

    out = aggregate_bureau_balance(bb)

    feature_cols = list(out.columns[1:])
    assert feature_cols == sorted(feature_cols)


def test_aggregate_bureau_balance_empty() -> None:
    bb = pd.DataFrame(columns=["SK_ID_BUREAU", "MONTHS_BALANCE", "STATUS"])

    out = aggregate_bureau_balance(bb)

    assert out.empty
    assert "SK_ID_BUREAU" in out.columns
    assert "BB_MONTHS_COUNT" in out.columns


def test_aggregate_bureau_balance_missing_status_raises() -> None:
    bb = pd.DataFrame({"SK_ID_BUREAU": [1], "MONTHS_BALANCE": [0]})

    with pytest.raises(ValueError, match="STATUS"):
        aggregate_bureau_balance(bb)


# ---------------------------------------------------------------------------
# merge_bureau_with_balance
# ---------------------------------------------------------------------------
def test_merge_preserves_all_bureau_rows() -> None:
    bureau = _build_bureau()
    bb_features = aggregate_bureau_balance(_build_bureau_balance())

    merged = merge_bureau_with_balance(bureau, bb_features)

    assert len(merged) == len(bureau)
    assert merged["SK_ID_BUREAU"].tolist() == bureau["SK_ID_BUREAU"].tolist()


def test_merge_fills_count_columns_with_zero() -> None:
    bureau = _build_bureau()
    bb_features = aggregate_bureau_balance(_build_bureau_balance())

    merged = merge_bureau_with_balance(bureau, bb_features)

    # Credit 4 has no balance history -> count columns become 0.
    row4 = merged.loc[merged["SK_ID_BUREAU"] == 4].iloc[0]
    assert row4["BB_MONTHS_COUNT"] == 0
    assert row4["BB_DPD_MONTHS_COUNT"] == 0
    assert row4["BB_STATUS_0_COUNT"] == 0


# ---------------------------------------------------------------------------
# aggregate_bureau_to_applicant
# ---------------------------------------------------------------------------
def test_aggregate_to_applicant_one_row_per_applicant() -> None:
    bureau = _build_bureau()
    bb_features = aggregate_bureau_balance(_build_bureau_balance())
    enriched = merge_bureau_with_balance(bureau, bb_features)

    out = aggregate_bureau_to_applicant(enriched)

    assert out.columns[0] == "SK_ID_CURR"
    assert sorted(out["SK_ID_CURR"].tolist()) == [100001, 100002, 100003]
    # No bureau id should leak into the applicant-level output.
    assert "SK_ID_BUREAU" not in out.columns


def test_aggregate_to_applicant_counts_and_ratios() -> None:
    bureau = _build_bureau()
    bb_features = aggregate_bureau_balance(_build_bureau_balance())
    enriched = merge_bureau_with_balance(bureau, bb_features)

    out = aggregate_bureau_to_applicant(enriched)

    row = out.loc[out["SK_ID_CURR"] == 100001].iloc[0]
    assert row["BUREAU_COUNT"] == 2
    # Applicant 100001 has one Active + one Closed credit.
    assert row["BUREAU_CREDIT_ACTIVE_ACTIVE_COUNT"] == 1
    assert row["BUREAU_CREDIT_ACTIVE_CLOSED_COUNT"] == 1
    assert row["BUREAU_ACTIVE_CREDIT_RATIO"] == pytest.approx(0.5)
    # Debt 40000 over credit 150000 (sum of 100000 + 50000).
    assert row["BUREAU_DEBT_CREDIT_RATIO"] == pytest.approx(40000.0 / 150000.0)
    assert row["BUREAU_AMT_CREDIT_SUM_SUM"] == pytest.approx(150000.0)


def test_aggregate_to_applicant_columns_sorted() -> None:
    bureau = _build_bureau()
    bb_features = aggregate_bureau_balance(_build_bureau_balance())
    enriched = merge_bureau_with_balance(bureau, bb_features)

    out = aggregate_bureau_to_applicant(enriched)

    feature_cols = list(out.columns[1:])
    assert feature_cols == sorted(feature_cols)


def test_aggregate_to_applicant_no_infinities() -> None:
    bureau = _build_bureau()
    bb_features = aggregate_bureau_balance(_build_bureau_balance())
    enriched = merge_bureau_with_balance(bureau, bb_features)

    out = aggregate_bureau_to_applicant(enriched)

    numeric = out.select_dtypes(include="number")
    assert not np.isinf(numeric.to_numpy()).any()


# ---------------------------------------------------------------------------
# build_bureau_features
# ---------------------------------------------------------------------------
def test_build_bureau_features_end_to_end() -> None:
    bureau = _build_bureau()
    bureau_balance = _build_bureau_balance()

    out = build_bureau_features(bureau, bureau_balance)

    assert out.columns[0] == "SK_ID_CURR"
    assert sorted(out["SK_ID_CURR"].tolist()) == [100001, 100002, 100003]
    assert out["SK_ID_CURR"].is_unique
    feature_cols = list(out.columns[1:])
    assert feature_cols == sorted(feature_cols)
    assert "SK_ID_BUREAU" not in out.columns


def test_build_bureau_features_mergeable_with_application() -> None:
    bureau = _build_bureau()
    bureau_balance = _build_bureau_balance()
    bureau_features = build_bureau_features(bureau, bureau_balance)

    application = pd.DataFrame(
        {
            "SK_ID_CURR": [100001, 100002, 100003, 100004],
            "SOME_APP_FEATURE": [1.0, 2.0, 3.0, 4.0],
        }
    )

    merged = application.merge(bureau_features, on="SK_ID_CURR", how="left")

    # Row count of the application table is preserved.
    assert len(merged) == len(application)
    # Applicant without bureau history (100004) gets NaN bureau features.
    row = merged.loc[merged["SK_ID_CURR"] == 100004].iloc[0]
    assert math.isnan(row["BUREAU_COUNT"])


def test_build_bureau_features_missing_applicant_id_raises() -> None:
    bureau = _build_bureau().drop(columns=["SK_ID_CURR"])
    bureau_balance = _build_bureau_balance()

    with pytest.raises(ValueError, match="applicant id column"):
        build_bureau_features(bureau, bureau_balance)


def test_build_bureau_features_missing_bureau_id_raises() -> None:
    bureau = _build_bureau().drop(columns=["SK_ID_BUREAU"])
    bureau_balance = _build_bureau_balance()

    with pytest.raises(ValueError, match="bureau id column"):
        build_bureau_features(bureau, bureau_balance)


def test_build_bureau_features_balance_missing_bureau_id_raises() -> None:
    bureau = _build_bureau()
    bureau_balance = _build_bureau_balance().drop(columns=["SK_ID_BUREAU"])

    with pytest.raises(ValueError, match="bureau id column"):
        build_bureau_features(bureau, bureau_balance)


# ---------------------------------------------------------------------------
# save_bureau_features
# ---------------------------------------------------------------------------
def test_save_bureau_features_creates_parquet(tmp_path: Path) -> None:
    bureau = _build_bureau()
    bureau_balance = _build_bureau_balance()
    bureau_features = build_bureau_features(bureau, bureau_balance)

    output_path = tmp_path / "processed" / "bureau_features.parquet"

    out_path = save_bureau_features(bureau_features, output_path)

    assert out_path.exists()
    reloaded = pd.read_parquet(output_path)
    assert reloaded.shape == bureau_features.shape
    assert list(reloaded.columns) == list(bureau_features.columns)


# ---------------------------------------------------------------------------
# load_bureau_feature_config
# ---------------------------------------------------------------------------
def test_load_bureau_feature_config(tmp_path: Path) -> None:
    config_path = tmp_path / "features.yaml"
    config_path.write_text(
        "bureau_features:\n" "  output_path: data/processed/bureau_features.parquet\n",
        encoding="utf-8",
    )

    config = load_bureau_feature_config(config_path)

    assert config["output_path"] == "data/processed/bureau_features.parquet"
    assert config["id_column"] == "SK_ID_CURR"
    assert config["bureau_id_column"] == "SK_ID_BUREAU"


def test_load_bureau_feature_config_missing_section_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "features.yaml"
    config_path.write_text("id_column: SK_ID_CURR\n", encoding="utf-8")

    with pytest.raises(ValueError, match="bureau_features"):
        load_bureau_feature_config(config_path)


def test_load_bureau_feature_config_missing_output_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "features.yaml"
    config_path.write_text(
        "bureau_features:\n  id_column: SK_ID_CURR\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="output_path"):
        load_bureau_feature_config(config_path)
