from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.data.load_raw import load_data_config, load_raw_tables
from src.data.validate_schema import (
    validate_foreign_key_relationship,
    validate_non_empty,
    validate_raw_tables,
    validate_required_columns,
    validate_unique_key,
)


def _write_csv(path: Path, data: dict) -> None:
    pd.DataFrame(data).to_csv(path, index=False)


def _build_valid_config(raw_dir: Path) -> dict:
    return {
        "raw_data_dir": str(raw_dir),
        "tables": {
            "application_train": {
                "filename": "application_train.csv",
                "required_columns": ["SK_ID_CURR", "TARGET"],
                "unique_key": ["SK_ID_CURR"],
            },
            "application_test": {
                "filename": "application_test.csv",
                "required_columns": ["SK_ID_CURR"],
                "unique_key": ["SK_ID_CURR"],
            },
            "bureau": {
                "filename": "bureau.csv",
                "required_columns": ["SK_ID_CURR", "SK_ID_BUREAU"],
                "unique_key": ["SK_ID_BUREAU"],
            },
            "bureau_balance": {
                "filename": "bureau_balance.csv",
                "required_columns": ["SK_ID_BUREAU", "MONTHS_BALANCE", "STATUS"],
            },
        },
    }


def _write_valid_config(config_path: Path, raw_dir: Path) -> Path:
    config = _build_valid_config(raw_dir)
    with config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)
    return config_path


def _write_valid_raw_tables(raw_dir: Path) -> None:
    _write_csv(
        raw_dir / "application_train.csv",
        {
            "SK_ID_CURR": [100001, 100002],
            "TARGET": [0, 1],
        },
    )
    _write_csv(
        raw_dir / "application_test.csv",
        {
            "SK_ID_CURR": [100003, 100004],
        },
    )
    _write_csv(
        raw_dir / "bureau.csv",
        {
            "SK_ID_CURR": [100001, 100002],
            "SK_ID_BUREAU": [200001, 200002],
        },
    )
    _write_csv(
        raw_dir / "bureau_balance.csv",
        {
            "SK_ID_BUREAU": [200001, 200001, 200002],
            "MONTHS_BALANCE": [0, -1, 0],
            "STATUS": ["0", "1", "0"],
        },
    )


def test_validate_required_columns_success() -> None:
    df = pd.DataFrame({"SK_ID_CURR": [1, 2], "TARGET": [0, 1]})
    validate_required_columns(
        table_name="application_train",
        df=df,
        required_columns=["SK_ID_CURR", "TARGET"],
    )


def test_validate_required_columns_missing_column() -> None:
    df = pd.DataFrame({"SK_ID_CURR": [1, 2]})

    with pytest.raises(ValueError, match="missing required columns"):
        validate_required_columns(
            table_name="application_train",
            df=df,
            required_columns=["SK_ID_CURR", "TARGET"],
        )


def test_validate_non_empty_raises_on_empty_table() -> None:
    df = pd.DataFrame(columns=["SK_ID_CURR", "TARGET"])

    with pytest.raises(ValueError, match="is empty"):
        validate_non_empty("application_train", df)


def test_validate_unique_key_success() -> None:
    df = pd.DataFrame({"SK_ID_BUREAU": [10, 20, 30]})
    validate_unique_key(
        table_name="bureau",
        df=df,
        unique_key=["SK_ID_BUREAU"],
    )


def test_validate_unique_key_raises_on_duplicates() -> None:
    df = pd.DataFrame(
        {
            "SK_ID_BUREAU": [10, 10, 20],
            "SK_ID_CURR": [1, 1, 2],
        }
    )

    with pytest.raises(ValueError, match="duplicated rows"):
        validate_unique_key(
            table_name="bureau",
            df=df,
            unique_key=["SK_ID_BUREAU"],
        )


def test_validate_foreign_key_relationship_success() -> None:
    parent_df = pd.DataFrame({"SK_ID_BUREAU": [10, 20]})
    child_df = pd.DataFrame({"SK_ID_BUREAU": [10, 10, 20]})

    validate_foreign_key_relationship(
        child_df=child_df,
        child_column="SK_ID_BUREAU",
        parent_df=parent_df,
        parent_column="SK_ID_BUREAU",
        relationship_name="bureau_balance.SK_ID_BUREAU -> bureau.SK_ID_BUREAU",
    )


def test_validate_foreign_key_relationship_raises_on_orphans() -> None:
    parent_df = pd.DataFrame({"SK_ID_BUREAU": [10, 20]})
    child_df = pd.DataFrame({"SK_ID_BUREAU": [10, 30]})

    with pytest.raises(ValueError, match="Foreign key violation"):
        validate_foreign_key_relationship(
            child_df=child_df,
            child_column="SK_ID_BUREAU",
            parent_df=parent_df,
            parent_column="SK_ID_BUREAU",
            relationship_name="bureau_balance.SK_ID_BUREAU -> bureau.SK_ID_BUREAU",
        )


def test_validate_raw_tables_success(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    _write_valid_raw_tables(raw_dir)

    config_path = tmp_path / "data.yaml"
    _write_valid_config(config_path, raw_dir)

    config = load_data_config(config_path)
    tables = load_raw_tables(config_path)

    validate_raw_tables(tables, config)


def test_validate_raw_tables_missing_target_in_application_train(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    _write_csv(
        raw_dir / "application_train.csv",
        {
            "SK_ID_CURR": [100001, 100002],
            # TARGET intentionally missing
        },
    )
    _write_csv(
        raw_dir / "application_test.csv",
        {
            "SK_ID_CURR": [100003, 100004],
        },
    )
    _write_csv(
        raw_dir / "bureau.csv",
        {
            "SK_ID_CURR": [100001, 100002],
            "SK_ID_BUREAU": [200001, 200002],
        },
    )
    _write_csv(
        raw_dir / "bureau_balance.csv",
        {
            "SK_ID_BUREAU": [200001, 200002],
            "MONTHS_BALANCE": [0, 0],
            "STATUS": ["0", "1"],
        },
    )

    config_path = tmp_path / "data.yaml"
    _write_valid_config(config_path, raw_dir)

    config = load_data_config(config_path)
    tables = load_raw_tables(config_path)

    with pytest.raises(ValueError, match="TARGET"):
        validate_raw_tables(tables, config)


def test_validate_raw_tables_duplicate_application_train_key(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    _write_csv(
        raw_dir / "application_train.csv",
        {
            "SK_ID_CURR": [100001, 100001],
            "TARGET": [0, 1],
        },
    )
    _write_csv(
        raw_dir / "application_test.csv",
        {"SK_ID_CURR": [100003]},
    )
    _write_csv(
        raw_dir / "bureau.csv",
        {
            "SK_ID_CURR": [100001],
            "SK_ID_BUREAU": [200001],
        },
    )
    _write_csv(
        raw_dir / "bureau_balance.csv",
        {
            "SK_ID_BUREAU": [200001],
            "MONTHS_BALANCE": [0],
            "STATUS": ["0"],
        },
    )

    config_path = tmp_path / "data.yaml"
    _write_valid_config(config_path, raw_dir)

    config = load_data_config(config_path)
    tables = load_raw_tables(config_path)

    with pytest.raises(ValueError, match="duplicated rows"):
        validate_raw_tables(tables, config)

def test_validate_raw_tables_orphan_bureau_balance_key(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    _write_csv(
        raw_dir / "application_train.csv",
        {
            "SK_ID_CURR": [100001],
            "TARGET": [0],
        },
    )
    _write_csv(
        raw_dir / "application_test.csv",
        {"SK_ID_CURR": [100003]},
    )
    _write_csv(
        raw_dir / "bureau.csv",
        {
            "SK_ID_CURR": [100001],
            "SK_ID_BUREAU": [200001],
        },
    )
    _write_csv(
        raw_dir / "bureau_balance.csv",
        {
            "SK_ID_BUREAU": [999999],
            "MONTHS_BALANCE": [0],
            "STATUS": ["0"],
        },
    )

    config_path = tmp_path / "data.yaml"
    _write_valid_config(config_path, raw_dir)

    config = load_data_config(config_path)
    tables = load_raw_tables(config_path)

    with pytest.raises(ValueError, match="Foreign key violation"):
        validate_raw_tables(tables, config, strict_fk=True) 