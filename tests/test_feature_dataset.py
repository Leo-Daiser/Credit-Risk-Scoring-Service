"""Tests for the Phase 2.3 full feature dataset builder."""

import numpy as np
import pandas as pd
import pytest

from src.features.feature_dataset import (
    build_full_feature_dataset,
    merge_application_with_bureau_features,
    run_build_full_feature_dataset,
    save_full_feature_dataset,
    validate_feature_key_contract,
)


# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------
def _application_train() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1, 2, 3],
            "TARGET": [0, 1, 0],
            "AMT_CREDIT": [1000.0, 2000.0, 1500.0],
            "AGE_YEARS": [30.0, 45.0, 38.0],
        }
    )


def _application_test() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [4, 5],
            "AMT_CREDIT": [1200.0, 1800.0],
            "AGE_YEARS": [29.0, 51.0],
        }
    )


def _bureau() -> pd.DataFrame:
    # Note: only some applicants have bureau history.
    return pd.DataFrame(
        {
            "SK_ID_CURR": [1, 3, 4],
            "BUREAU_LOAN_COUNT": [2, 1, 3],
            "BUREAU_DEBT_CREDIT_RATIO": [0.5, 0.1, 0.8],
        }
    )


# ---------------------------------------------------------------------------
# validate_feature_key_contract
# ---------------------------------------------------------------------------
def test_validate_feature_key_contract_missing_id_raises():
    df = pd.DataFrame({"A": [1, 2]})
    with pytest.raises(ValueError, match="missing the required id column"):
        validate_feature_key_contract(df, "SK_ID_CURR", "app")


def test_validate_feature_key_contract_duplicate_id_raises():
    df = pd.DataFrame({"SK_ID_CURR": [1, 1, 2]})
    with pytest.raises(ValueError, match="duplicate"):
        validate_feature_key_contract(df, "SK_ID_CURR", "app")


# ---------------------------------------------------------------------------
# merge_application_with_bureau_features
# ---------------------------------------------------------------------------
def test_merge_application_with_bureau_preserves_row_count():
    app = _application_train()
    bureau = _bureau()
    merged = merge_application_with_bureau_features(app, bureau)
    assert len(merged) == len(app)
    # Applicant 2 has no bureau history -> NaN bureau features (not imputed).
    row2 = merged.loc[merged["SK_ID_CURR"] == 2].iloc[0]
    assert np.isnan(row2["BUREAU_LOAN_COUNT"])


def test_merge_application_with_bureau_no_row_explosion():
    app = _application_train()
    # Bureau is supposed to be applicant-level (unique). A duplicate must fail
    # the key contract rather than silently exploding the rows.
    bureau = pd.concat([_bureau(), _bureau().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        merge_application_with_bureau_features(app, bureau)


def test_merge_application_with_bureau_column_order_with_target():
    app = _application_train()
    bureau = _bureau()
    merged = merge_application_with_bureau_features(app, bureau)
    assert merged.columns[0] == "SK_ID_CURR"
    assert merged.columns[1] == "TARGET"
    feature_cols = list(merged.columns[2:])
    assert feature_cols == sorted(feature_cols)


# ---------------------------------------------------------------------------
# build_full_feature_dataset
# ---------------------------------------------------------------------------
def test_build_full_feature_dataset_contract():
    train_df, test_df = build_full_feature_dataset(
        _application_train(), _application_test(), _bureau()
    )
    assert list(train_df.columns[:2]) == ["SK_ID_CURR", "TARGET"]
    assert test_df.columns[0] == "SK_ID_CURR"
    assert "TARGET" not in test_df.columns

    train_feature_cols = [
        c for c in train_df.columns if c not in ("SK_ID_CURR", "TARGET")
    ]
    test_feature_cols = [c for c in test_df.columns if c != "SK_ID_CURR"]
    assert train_feature_cols == test_feature_cols


def test_build_full_feature_dataset_preserves_rows():
    app_train = _application_train()
    app_test = _application_test()
    train_df, test_df = build_full_feature_dataset(app_train, app_test, _bureau())
    assert len(train_df) == len(app_train)
    assert len(test_df) == len(app_test)


def test_build_full_feature_dataset_missing_target_raises():
    app_train = _application_train().drop(columns=["TARGET"])
    with pytest.raises(ValueError, match="must contain the target column"):
        build_full_feature_dataset(app_train, _application_test(), _bureau())


def test_build_full_feature_dataset_drops_target_from_test_if_present():
    app_test = _application_test().copy()
    app_test["TARGET"] = [0, 1]
    train_df, test_df = build_full_feature_dataset(
        _application_train(), app_test, _bureau()
    )
    assert "TARGET" not in test_df.columns


def test_build_full_feature_dataset_replaces_infinities():
    app_train = _application_train().copy()
    app_train.loc[0, "AMT_CREDIT"] = np.inf
    train_df, _ = build_full_feature_dataset(app_train, _application_test(), _bureau())
    assert not np.isinf(train_df["AMT_CREDIT"]).any()
    assert np.isnan(train_df.loc[train_df["SK_ID_CURR"] == 1, "AMT_CREDIT"]).all()


# ---------------------------------------------------------------------------
# save / run end-to-end
# ---------------------------------------------------------------------------
def test_save_full_feature_dataset_creates_parquet(tmp_path):
    train_df, test_df = build_full_feature_dataset(
        _application_train(), _application_test(), _bureau()
    )
    train_path = tmp_path / "nested" / "train_features.parquet"
    test_path = tmp_path / "nested" / "test_features.parquet"
    save_full_feature_dataset(train_df, test_df, train_path, test_path)

    assert train_path.exists()
    assert test_path.exists()
    pd.testing.assert_frame_equal(pd.read_parquet(train_path), train_df)
    pd.testing.assert_frame_equal(pd.read_parquet(test_path), test_df)


def test_run_build_full_feature_dataset_end_to_end(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    _application_train().to_parquet(processed / "app_train.parquet", index=False)
    _application_test().to_parquet(processed / "app_test.parquet", index=False)
    _bureau().to_parquet(processed / "bureau.parquet", index=False)

    config = {
        "full_feature_dataset": {
            "id_column": "SK_ID_CURR",
            "target_column": "TARGET",
            "application_train_features_path": str(processed / "app_train.parquet"),
            "application_test_features_path": str(processed / "app_test.parquet"),
            "bureau_features_path": str(processed / "bureau.parquet"),
            "output_train_path": str(processed / "train_features.parquet"),
            "output_test_path": str(processed / "test_features.parquet"),
        }
    }
    import yaml

    config_path = tmp_path / "features.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    summary = run_build_full_feature_dataset(feature_config_path=config_path)
    assert (processed / "train_features.parquet").exists()
    assert (processed / "test_features.parquet").exists()
    assert summary["train_shape"][0] == 3
    assert summary["test_shape"][0] == 2
    assert summary["id_column"] == "SK_ID_CURR"
    assert summary["target_column"] == "TARGET"
