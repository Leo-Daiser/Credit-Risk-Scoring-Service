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


def load_raw_tables(
    config_path: str | Path,
    table_names: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Load raw CSV tables described in the data config.

    Args:
        config_path: Path to the data config (e.g. ``configs/data.yaml``).
        table_names: Optional list of table names to load. When ``None``
            (the default) all tables in the config are loaded, preserving the
            previous behavior. When provided, only the requested tables are
            loaded — useful for stages that need a subset, e.g.
            ``["application_train", "application_test"]``.

    Returns:
        Mapping of table name to its loaded ``DataFrame``.
    """
    config = load_data_config(config_path)
    table_paths = resolve_table_paths(config)

    if table_names is not None:
        missing_tables = [name for name in table_names if name not in table_paths]
        if missing_tables:
            raise ValueError(
                f"Unknown table(s) requested: {missing_tables}. "
                f"Available tables: {sorted(table_paths)}."
            )
        table_paths = {name: table_paths[name] for name in table_names}

    tables: dict[str, pd.DataFrame] = {}

    for table_name, table_path in table_paths.items():
        if not table_path.exists():
            raise FileNotFoundError(
                f"Raw data file for table '{table_name}' not found: {table_path}"
            )

        df = pd.read_csv(table_path)
        tables[table_name] = df

    return tables