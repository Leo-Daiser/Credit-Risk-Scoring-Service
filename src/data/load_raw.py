from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def load_data_config(config_path: str | Path) -> dict[str, Any]:
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Data config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("Data config must be a dictionary.")

    if "raw_data_dir" not in config:
        raise ValueError("Data config must contain 'raw_data_dir'.")

    if "tables" not in config or not isinstance(config["tables"], dict):
        raise ValueError("Data config must contain a 'tables' dictionary.")

    return config


def resolve_table_paths(config: dict[str, Any]) -> dict[str, Path]:
    raw_data_dir = Path(config["raw_data_dir"])
    table_paths: dict[str, Path] = {}

    for table_name, table_cfg in config["tables"].items():
        filename = table_cfg.get("filename")
        if not filename:
            raise ValueError(f"Missing filename for table '{table_name}'.")
        table_paths[table_name] = raw_data_dir / filename

    return table_paths


def load_raw_tables(config_path: str | Path) -> dict[str, pd.DataFrame]:
    config = load_data_config(config_path)
    table_paths = resolve_table_paths(config)

    tables: dict[str, pd.DataFrame] = {}

    for table_name, table_path in table_paths.items():
        if not table_path.exists():
            raise FileNotFoundError(
                f"Raw data file for table '{table_name}' not found: {table_path}"
            )

        df = pd.read_csv(table_path)
        tables[table_name] = df

    return tables