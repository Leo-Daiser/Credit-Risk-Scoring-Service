import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features.application_features import (
    add_application_derived_features,
    build_application_features,
    clean_application_table,
    safe_divide,
    save_application_features,
)

DAYS_EMPLOYED_ANOMALY = 365243


def _build_application_train() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [100001, 100002, 100003],
            "TARGET": [0, 1, 0],
            "AMT_INCOME_TOTAL": [100000.0, 200000.0, 0.0],
            "AMT_CREDIT": [500000.0, 1000000.0, 300000.0],
            "AMT_ANNUITY": [25000.0, 50000.0, 15000.0],
            "DAYS_BIRTH": [-12000, -15000, -9000],
            "DAYS_EMPLOYED": [-2000, DAYS_EMPLOYED_ANOMALY, -500],
            "CNT_FAM_MEMBERS": [2.0, 4.0, 0.0],
            "EXT_SOURCE_1": [0.5, 0.7, np.nan],
            "EXT_SOURCE_2": [0.6, 0.8, 0.4],
            "EXT_SOURCE_3": [0.55, np.nan, 0.45],
        }
    )


def _build_application_test() -> pd.DataFrame:
    df = _build_application_train().drop(columns=["TARGET"])
    df["SK_ID_CURR"] = [200001, 200002, 200003]
    return df


# ---------------------------------------------------------------------------
# safe_divide
# ---------------------------------------------------------------------------
def test_safe_divide_handles_zero_denominator_scalar() -> None:
    result = safe_divide(10, 0)
    assert isinstance(result, float)
    assert math.isnan(result)


def test_safe_divide_handles_zero_denominator_series() -> None:
    num = pd.Series([10.0, 20.0, 30.0])
    den = pd.Series([2.0, 0.0, 5.0])

    result = safe_divide(num, den)

    assert result.iloc[0] == 5.0
    assert math.isnan(result.iloc[1])
    assert result.iloc[2] == 6.0


# ---------------------------------------------------------------------------
# clean_application_table
# ---------------------------------------------------------------------------
def test_clean_application_table_replaces_days_employed_anomaly() -> None:
    df = _build_application_train()

    cleaned = clean_application_table(
        df, days_employed_anomaly_value=DAYS_EMPLOYED_ANOMALY
    )

    assert cleaned["DAYS_EMPLOYED"].isna().sum() == 1
    assert not (cleaned["DAYS_EMPLOYED"] == DAYS_EMPLOYED_ANOMALY).any()
    # Original frame must not be mutated.
    assert (df["DAYS_EMPLOYED"] == DAYS_EMPLOYED_ANOMALY).sum() == 1
    # Row count preserved.
    assert len(cleaned) == len(df)


def test_clean_application_table_replaces_infinities() -> None:
    df = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 2],
            "SOME_COL": [np.inf, -np.inf],
        }
    )

    cleaned = clean_application_table(df)

    assert cleaned["SOME_COL"].isna().all()


# ---------------------------------------------------------------------------
# add_application_derived_features
# ---------------------------------------------------------------------------
def test_derived_features_created_correctly() -> None:
    df = clean_application_table(_build_application_train())

    out = add_application_derived_features(df)

    expected_columns = {
        "CREDIT_INCOME_RATIO",
        "ANNUITY_INCOME_RATIO",
        "CREDIT_TERM",
        "DAYS_EMPLOYED_RATIO",
        "INCOME_PER_FAM_MEMBER",
        "AGE_YEARS",
        "EMPLOYMENT_YEARS",
        "EXT_SOURCE_MEAN",
        "EXT_SOURCE_STD",
        "EXT_SOURCE_MIN",
        "EXT_SOURCE_MAX",
    }
    assert expected_columns.issubset(out.columns)

    # Spot-check the computed values for the first row.
    assert out["CREDIT_INCOME_RATIO"].iloc[0] == pytest.approx(500000.0 / 100000.0)
    assert out["ANNUITY_INCOME_RATIO"].iloc[0] == pytest.approx(25000.0 / 100000.0)
    assert out["CREDIT_TERM"].iloc[0] == pytest.approx(25000.0 / 500000.0)
    assert out["DAYS_EMPLOYED_RATIO"].iloc[0] == pytest.approx(-2000 / -12000)
    assert out["INCOME_PER_FAM_MEMBER"].iloc[0] == pytest.approx(100000.0 / 2.0)
    assert out["AGE_YEARS"].iloc[0] == pytest.approx(12000 / 365.25)
    assert out["EMPLOYMENT_YEARS"].iloc[0] == pytest.approx(2000 / 365.25)
    assert out["EXT_SOURCE_MEAN"].iloc[0] == pytest.approx(np.mean([0.5, 0.6, 0.55]))
    assert out["EXT_SOURCE_MIN"].iloc[0] == pytest.approx(0.5)
    assert out["EXT_SOURCE_MAX"].iloc[0] == pytest.approx(0.6)


def test_derived_features_use_safe_division() -> None:
    df = clean_application_table(_build_application_train())

    out = add_application_derived_features(df)

    # Third applicant has AMT_INCOME_TOTAL == 0 and CNT_FAM_MEMBERS == 0.
    assert math.isnan(out["CREDIT_INCOME_RATIO"].iloc[2])
    assert math.isnan(out["ANNUITY_INCOME_RATIO"].iloc[2])
    assert math.isnan(out["INCOME_PER_FAM_MEMBER"].iloc[2])
    # No infinities should remain.
    numeric = out.select_dtypes(include="number")
    assert not np.isinf(numeric.to_numpy()).any()


# ---------------------------------------------------------------------------
# build_application_features
# ---------------------------------------------------------------------------
def test_build_preserves_row_counts() -> None:
    train = _build_application_train()
    test = _build_application_test()

    train_features, test_features = build_application_features(train, test)

    assert len(train_features) == len(train)
    assert len(test_features) == len(test)


def test_build_preserves_id_column() -> None:
    train = _build_application_train()
    test = _build_application_test()

    train_features, test_features = build_application_features(train, test)

    assert "SK_ID_CURR" in train_features.columns
    assert "SK_ID_CURR" in test_features.columns
    assert train_features["SK_ID_CURR"].tolist() == train["SK_ID_CURR"].tolist()
    assert test_features["SK_ID_CURR"].tolist() == test["SK_ID_CURR"].tolist()


def test_target_only_in_train_features() -> None:
    train = _build_application_train()
    test = _build_application_test()

    train_features, test_features = build_application_features(train, test)

    assert "TARGET" in train_features.columns
    assert "TARGET" not in test_features.columns


def test_train_test_feature_columns_match_except_target() -> None:
    train = _build_application_train()
    test = _build_application_test()

    train_features, test_features = build_application_features(train, test)

    train_cols = set(train_features.columns) - {"TARGET"}
    test_cols = set(test_features.columns)
    assert train_cols == test_cols


def test_missing_target_in_train_raises() -> None:
    train = _build_application_train().drop(columns=["TARGET"])
    test = _build_application_test()

    with pytest.raises(ValueError, match="target column"):
        build_application_features(train, test)


def test_missing_id_in_train_raises() -> None:
    train = _build_application_train().drop(columns=["SK_ID_CURR"])
    test = _build_application_test()

    with pytest.raises(
        ValueError, match=r"Train table is missing the ID column 'SK_ID_CURR'"
    ):
        build_application_features(train, test)


def test_missing_id_in_test_raises() -> None:
    train = _build_application_train()
    test = _build_application_test().drop(columns=["SK_ID_CURR"])

    with pytest.raises(
        ValueError, match=r"Test table is missing the ID column 'SK_ID_CURR'"
    ):
        build_application_features(train, test)


def test_train_output_column_order_starts_with_id_then_target() -> None:
    train = _build_application_train()
    test = _build_application_test()

    train_features, _ = build_application_features(train, test)

    assert list(train_features.columns[:2]) == ["SK_ID_CURR", "TARGET"]
    # Remaining feature columns are deterministically sorted.
    feature_cols = list(train_features.columns[2:])
    assert feature_cols == sorted(feature_cols)


def test_test_output_column_order_starts_with_id() -> None:
    train = _build_application_train()
    test = _build_application_test()

    _, test_features = build_application_features(train, test)

    assert test_features.columns[0] == "SK_ID_CURR"
    assert "TARGET" not in test_features.columns
    # Remaining feature columns are deterministically sorted.
    feature_cols = list(test_features.columns[1:])
    assert feature_cols == sorted(feature_cols)


def test_train_test_feature_order_matches_except_target() -> None:
    train = _build_application_train()
    test = _build_application_test()

    train_features, test_features = build_application_features(train, test)

    # Drop TARGET from train; the remaining ordered columns must be identical.
    train_cols = [c for c in train_features.columns if c != "TARGET"]
    assert train_cols == list(test_features.columns)


def test_train_test_feature_mismatch_raises() -> None:
    train = _build_application_train()
    test = _build_application_test()
    # Introduce a column present only in the test table so derived/raw
    # feature sets diverge.
    test["EXTRA_COLUMN"] = 1.0

    with pytest.raises(ValueError, match="do not match"):
        build_application_features(train, test)


# ---------------------------------------------------------------------------
# save_application_features
# ---------------------------------------------------------------------------
def test_saving_features_creates_parquet_files(tmp_path: Path) -> None:
    train = _build_application_train()
    test = _build_application_test()

    train_features, test_features = build_application_features(train, test)

    train_path = tmp_path / "processed" / "application_train_features.parquet"
    test_path = tmp_path / "processed" / "application_test_features.parquet"

    out_train, out_test = save_application_features(
        train_features, test_features, train_path, test_path
    )

    assert out_train.exists()
    assert out_test.exists()

    reloaded_train = pd.read_parquet(train_path)
    reloaded_test = pd.read_parquet(test_path)
    assert reloaded_train.shape == train_features.shape
    assert reloaded_test.shape == test_features.shape
    assert "TARGET" in reloaded_train.columns
    assert "TARGET" not in reloaded_test.columns
