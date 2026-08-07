from pathlib import Path
from typing import Any

import pandas as pd

from src.data.load_raw import load_data_config, resolve_table_paths


def validate_required_columns(
    table_name: str,
    df: pd.DataFrame,
    required_columns: list[str],
) -> None:
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Table '{table_name}' is missing required columns: {missing}")


def validate_non_empty(table_name: str, df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError(f"Table '{table_name}' is empty.")


def validate_unique_key(
    table_name: str,
    df: pd.DataFrame,
    unique_key: list[str] | None,
) -> None:
    if not unique_key:
        return

    duplicated_mask = df.duplicated(subset=unique_key, keep=False)
    if duplicated_mask.any():
        dup_count = int(duplicated_mask.sum())
        raise ValueError(
            f"Table '{table_name}' has {dup_count} duplicated rows for unique key {unique_key}."
        )


def validate_foreign_key_relationship(
    child_df: pd.DataFrame,
    child_column: str,
    parent_df: pd.DataFrame,
    parent_column: str,
    relationship_name: str,
    strict: bool = True,
) -> dict[str, Any]:
    child_values = set(child_df[child_column].dropna().unique())
    parent_values = set(parent_df[parent_column].dropna().unique())

    orphan_values = child_values - parent_values
    orphan_count = len(orphan_values)
    child_count = len(child_values)
    orphan_ratio = orphan_count / child_count if child_count > 0 else 0.0

    result = {
        "relationship_name": relationship_name,
        "child_unique_keys": child_count,
        "parent_unique_keys": len(parent_values),
        "orphan_count": orphan_count,
        "orphan_ratio": orphan_ratio,
        "sample_orphans": list(sorted(orphan_values))[:10],
    }

    if strict and orphan_count > 0:
        raise ValueError(
            f"Foreign key violation in {relationship_name}: "
            f"{orphan_count} child keys are missing in parent table."
        )

    return result


def validate_raw_tables(
    tables: dict[str, pd.DataFrame],
    config: dict[str, Any],
    strict_fk: bool = False,
) -> dict[str, Any]:
    table_configs = config["tables"]

    for table_name, table_cfg in table_configs.items():
        if table_name not in tables:
            raise ValueError(f"Table '{table_name}' was not loaded.")

        df = tables[table_name]
        validate_non_empty(table_name, df)
        validate_required_columns(
            table_name=table_name,
            df=df,
            required_columns=table_cfg.get("required_columns", []),
        )
        validate_unique_key(
            table_name=table_name,
            df=df,
            unique_key=table_cfg.get("unique_key"),
        )

    fk_report = validate_foreign_key_relationship(
        child_df=tables["bureau_balance"],
        child_column="SK_ID_BUREAU",
        parent_df=tables["bureau"],
        parent_column="SK_ID_BUREAU",
        relationship_name="bureau_balance.SK_ID_BUREAU -> bureau.SK_ID_BUREAU",
        strict=strict_fk,
    )

    return {"fk_report": fk_report}


def validate_configured_raw_data(
    config_path: str | Path,
    strict_fk: bool = False,
) -> dict[str, Any]:
    """Validate every configured CSV without loading the wide tables together.

    Only columns needed by data contracts are materialized. This keeps memory
    bounded even for the multi-gigabyte Home Credit history tables.
    """
    config = load_data_config(config_path)
    table_paths = resolve_table_paths(config)
    relationships = config.get("relationships", [])
    if not isinstance(relationships, list):
        raise ValueError("Data config 'relationships' must be a list.")

    relationship_columns: dict[str, set[str]] = {table_name: set() for table_name in table_paths}
    for relationship in relationships:
        if not isinstance(relationship, dict):
            raise ValueError("Each data relationship must be a dictionary.")
        child_table = str(relationship["child_table"])
        parent_tables = [str(name) for name in relationship["parent_tables"]]
        if child_table not in table_paths or any(name not in table_paths for name in parent_tables):
            raise ValueError(f"Relationship references an unknown table: {relationship}.")
        relationship_columns[child_table].add(str(relationship["child_column"]))
        for parent_table in parent_tables:
            relationship_columns[parent_table].add(str(relationship["parent_column"]))

    key_sets: dict[tuple[str, str], set[Any]] = {}
    table_reports: dict[str, dict[str, Any]] = {}
    for table_name, table_cfg in config["tables"].items():
        path = table_paths[table_name]
        if not path.exists():
            raise FileNotFoundError(f"Raw data file for table '{table_name}' not found: {path}")

        header = pd.read_csv(path, nrows=0)
        validate_required_columns(
            table_name,
            header,
            table_cfg.get("required_columns", []),
        )
        needed_columns = set(table_cfg.get("required_columns", []))
        needed_columns.update(table_cfg.get("unique_key") or [])
        needed_columns.update(relationship_columns[table_name])
        frame = pd.read_csv(path, usecols=sorted(needed_columns))
        validate_non_empty(table_name, frame)
        validate_unique_key(table_name, frame, table_cfg.get("unique_key"))

        for column in relationship_columns[table_name]:
            key_sets[(table_name, column)] = set(frame[column].dropna().unique())
        table_reports[table_name] = {
            "rows": int(len(frame)),
            "columns": int(len(header.columns)),
            "validated_columns": sorted(needed_columns),
        }

    relationship_reports: list[dict[str, Any]] = []
    for relationship in relationships:
        child_table = str(relationship["child_table"])
        child_column = str(relationship["child_column"])
        parent_column = str(relationship["parent_column"])
        parent_tables = [str(name) for name in relationship["parent_tables"]]
        child_values = key_sets[(child_table, child_column)]
        parent_values: set[Any] = set()
        for parent_table in parent_tables:
            parent_values.update(key_sets[(parent_table, parent_column)])
        orphan_values = child_values - parent_values
        report = {
            "relationship_name": str(relationship["name"]),
            "child_unique_keys": len(child_values),
            "parent_unique_keys": len(parent_values),
            "orphan_count": len(orphan_values),
            "orphan_ratio": len(orphan_values) / len(child_values) if child_values else 0.0,
            "sample_orphans": list(sorted(orphan_values))[:10],
        }
        if strict_fk and orphan_values:
            raise ValueError(
                f"Foreign key violation in {report['relationship_name']}: "
                f"{len(orphan_values)} child keys are missing in parent tables."
            )
        relationship_reports.append(report)

    return {
        "table_reports": table_reports,
        "relationship_reports": relationship_reports,
    }
