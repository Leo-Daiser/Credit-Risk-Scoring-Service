from typing import Any

import pandas as pd


def validate_required_columns(
    table_name: str,
    df: pd.DataFrame,
    required_columns: list[str],
) -> None:
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"Table '{table_name}' is missing required columns: {missing}"
        )


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
            f"Table '{table_name}' has {dup_count} duplicated rows "
            f"for unique key {unique_key}."
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