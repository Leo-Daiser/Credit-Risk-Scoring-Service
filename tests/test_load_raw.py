from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.data.load_raw import (
    load_data_config,
    load_raw_tables,
    resolve_table_paths,
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


def test_load_data_config_success(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    config_path = tmp_path / "data.yaml"
    _write_valid_config(config_path, raw_dir)

    config = load_data_config(config_path)

    assert isinstance(config, dict)
    assert config["raw_data_dir"] == str(raw_dir)
    assert "tables" in config
    assert set(config["tables"].keys()) == {
        "application_train",
        "application_test",
        "bureau",
        "bureau_balance",
    }


def test_load_data_config_file_not_found() -> None:
    with pytest.raises(FileNotFoundError, match="Data config not found"):
        load_data_config("configs/does_not_exist.yaml")


def test_resolve_table_paths_success(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    config = _build_valid_config(raw_dir)
    table_paths = resolve_table_paths(config)

    assert table_paths["application_train"] == raw_dir / "application_train.csv"
    assert table_paths["application_test"] == raw_dir / "application_test.csv"
    assert table_paths["bureau"] == raw_dir / "bureau.csv"
    assert table_paths["bureau_balance"] == raw_dir / "bureau_balance.csv"


def test_load_raw_tables_success(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    _write_valid_raw_tables(raw_dir)

    config_path = tmp_path / "data.yaml"
    _write_valid_config(config_path, raw_dir)

    tables = load_raw_tables(config_path)

    assert set(tables.keys()) == {
        "application_train",
        "application_test",
        "bureau",
        "bureau_balance",
    }
    assert tables["application_train"].shape == (2, 2)
    assert tables["application_test"].shape == (2, 1)
    assert tables["bureau"].shape == (2, 2)
    assert tables["bureau_balance"].shape == (3, 3)


def test_load_raw_tables_missing_file(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    _write_csv(
        raw_dir / "application_train.csv",
        {"SK_ID_CURR": [1], "TARGET": [0]},
    )
    _write_csv(
        raw_dir / "application_test.csv",
        {"SK_ID_CURR": [2]},
    )
    _write_csv(
        raw_dir / "bureau.csv",
        {"SK_ID_CURR": [1], "SK_ID_BUREAU": [10]},
    )
    # bureau_balance.csv intentionally missing

    config_path = tmp_path / "data.yaml"
    _write_valid_config(config_path, raw_dir)

    with pytest.raises(FileNotFoundError, match="bureau_balance"):
        load_raw_tables(config_path)