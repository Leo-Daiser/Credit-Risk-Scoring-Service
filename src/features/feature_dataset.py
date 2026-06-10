"""Full train/test ML feature dataset builder (Phase 2.3).

This module assembles the final modelling datasets from the per-table feature
parquet files produced in earlier phases:

* ``application_train_features.parquet`` / ``application_test_features.parquet``
  (Phase 2.1, application-level features)
* ``bureau_features.parquet`` (Phase 2.2, applicant-level bureau aggregates)

The application feature tables are left-joined with the bureau feature table on
``SK_ID_CURR`` to produce::

    train_features.parquet  ->  SK_ID_CURR | TARGET | <features...>
    test_features.parquet   ->  SK_ID_CURR | <features...>

No imputation, encoding or scaling happens here — that is the job of the model
training pipeline (Phase 3.1+). This layer only merges, enforces the key
contract, fixes the column order and replaces infinities with ``NaN`` so the
downstream pipeline has clean, deterministic inputs.

Real Kaggle CSVs and every generated parquet output are never committed (see
``.gitignore``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

DEFAULT_ID_COLUMN = "SK_ID_CURR"
DEFAULT_TARGET_COLUMN = "TARGET"

# Keys that must be present inside the ``full_feature_dataset`` config section.
_REQUIRED_CONFIG_KEYS = (
    "id_column",
    "target_column",
    "application_train_features_path",
    "application_test_features_path",
    "bureau_features_path",
    "output_train_path",
    "output_test_path",
)


def load_full_feature_dataset_config(config_path: str | Path) -> dict[str, Any]:
    """Load and validate the feature config, ensuring a ``full_feature_dataset`` section.

    Args:
        config_path: Path to ``configs/features.yaml``.

    Returns:
        The full parsed configuration dictionary (the caller reads the
        ``full_feature_dataset`` section from it).

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config is malformed or the section / keys are missing.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Feature config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("Feature config must be a dictionary.")

    if "full_feature_dataset" not in config:
        raise ValueError(
            "Feature config must contain a 'full_feature_dataset' section."
        )

    dataset_config = config["full_feature_dataset"]
    if not isinstance(dataset_config, dict):
        raise ValueError("Feature config 'full_feature_dataset' must be a dictionary.")

    for required_key in _REQUIRED_CONFIG_KEYS:
        if required_key not in dataset_config:
            raise ValueError(
                "Feature config 'full_feature_dataset' must contain "
                f"'{required_key}'."
            )

    return config


def load_feature_parquet(path: str | Path) -> pd.DataFrame:
    """Read a feature parquet file into a DataFrame.

    Args:
        path: Path to the parquet file.

    Returns:
        The loaded :class:`pandas.DataFrame`.

    Raises:
        FileNotFoundError: With a clear message if the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Feature parquet file not found: {path}. Generate the upstream "
            "feature datasets first (see build-application-features / "
            "build-bureau-features)."
        )
    return pd.read_parquet(path)


def validate_feature_key_contract(
    df: pd.DataFrame,
    id_column: str,
    dataset_name: str,
) -> None:
    """Validate the join-key contract for a feature table.

    The ``id_column`` must exist and must not contain duplicate values.

    Args:
        df: The feature table to validate.
        id_column: The expected unique id column (e.g. ``SK_ID_CURR``).
        dataset_name: Human-readable name used in error messages.

    Raises:
        ValueError: If the id column is missing or contains duplicates.
    """
    if id_column not in df.columns:
        raise ValueError(
            f"{dataset_name} is missing the required id column '{id_column}'."
        )

    duplicate_count = int(df[id_column].duplicated().sum())
    if duplicate_count > 0:
        raise ValueError(
            f"{dataset_name} contains {duplicate_count} duplicate "
            f"'{id_column}' values; the key contract requires it to be unique."
        )


def _order_columns(
    df: pd.DataFrame,
    id_column: str,
    target_column: str,
) -> pd.DataFrame:
    """Return ``df`` with a deterministic column order.

    ``id_column`` first, ``target_column`` second (only if present), then every
    other column sorted alphabetically.
    """
    other_columns = sorted(c for c in df.columns if c not in (id_column, target_column))
    ordered = [id_column]
    if target_column in df.columns:
        ordered.append(target_column)
    ordered.extend(other_columns)
    return df[ordered]


def merge_application_with_bureau_features(
    application_features: pd.DataFrame,
    bureau_features: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
) -> pd.DataFrame:
    """Left-join application features with applicant-level bureau features.

    The application row count is preserved (no row explosion). Applicants
    without any bureau history keep ``NaN`` bureau feature values — no
    imputation or encoding happens here.

    The output keeps ``SK_ID_CURR`` as the first column and ``TARGET`` second
    when it is present in the application table.

    Args:
        application_features: Application-level feature table (train or test).
        bureau_features: Applicant-level bureau feature table.
        id_column: Join key, defaults to ``SK_ID_CURR``.

    Returns:
        The merged feature table.

    Raises:
        ValueError: If either input violates the key contract or the merge
            changes the application row count.
    """
    validate_feature_key_contract(
        application_features, id_column, "application_features"
    )
    validate_feature_key_contract(bureau_features, id_column, "bureau_features")

    n_before = len(application_features)

    # Avoid pulling a duplicate id column in from the bureau side.
    bureau_cols = [c for c in bureau_features.columns if c != id_column]
    merged = application_features.merge(
        bureau_features[[id_column, *bureau_cols]],
        on=id_column,
        how="left",
        validate="one_to_one",
    )

    if len(merged) != n_before:
        raise ValueError(
            "merge_application_with_bureau_features changed the application "
            f"row count ({n_before} -> {len(merged)}); check for duplicate "
            f"'{id_column}' values."
        )

    return _order_columns(merged, id_column, DEFAULT_TARGET_COLUMN)


def build_full_feature_dataset(
    application_train_features: pd.DataFrame,
    application_test_features: pd.DataFrame,
    bureau_features: pd.DataFrame,
    id_column: str = DEFAULT_ID_COLUMN,
    target_column: str = DEFAULT_TARGET_COLUMN,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the final train/test ML feature datasets.

    Steps:

    1. Validate the key contract for all three input tables.
    2. Require ``TARGET`` in the train table; drop ``TARGET`` from the test
       table if it happens to be present (it is not required there).
    3. Left-join train/test application features with bureau features.
    4. Enforce a deterministic column order (``SK_ID_CURR`` first, ``TARGET``
       second when present, the rest sorted alphabetically).
    5. Replace ``inf`` / ``-inf`` with ``NaN``.

    No imputation / encoding / scaling happens here.

    Returns:
        A ``(train_df, test_df)`` tuple where ``train_df`` follows the
        ``SK_ID_CURR | TARGET | features...`` contract and ``test_df`` follows
        the ``SK_ID_CURR | features...`` contract with matching feature columns.

    Raises:
        ValueError: If a key contract is violated, ``TARGET`` is missing from
            train, or the train/test feature columns do not match.
    """
    validate_feature_key_contract(
        application_train_features, id_column, "application_train_features"
    )
    validate_feature_key_contract(
        application_test_features, id_column, "application_test_features"
    )
    validate_feature_key_contract(bureau_features, id_column, "bureau_features")

    if target_column not in application_train_features.columns:
        raise ValueError(
            "application_train_features must contain the target column "
            f"'{target_column}'."
        )

    test_features = application_test_features
    if target_column in test_features.columns:
        # TARGET is not required for the test set; drop it if present.
        test_features = test_features.drop(columns=[target_column])

    train_df = merge_application_with_bureau_features(
        application_train_features, bureau_features, id_column=id_column
    )
    test_df = merge_application_with_bureau_features(
        test_features, bureau_features, id_column=id_column
    )

    train_df = train_df.replace([np.inf, -np.inf], np.nan)
    test_df = test_df.replace([np.inf, -np.inf], np.nan)

    # The feature columns (everything except the id and target) must match.
    train_feature_cols = [
        c for c in train_df.columns if c not in (id_column, target_column)
    ]
    test_feature_cols = [c for c in test_df.columns if c != id_column]
    if train_feature_cols != test_feature_cols:
        missing_in_test = sorted(set(train_feature_cols) - set(test_feature_cols))
        missing_in_train = sorted(set(test_feature_cols) - set(train_feature_cols))
        raise ValueError(
            "Train and test feature columns must match (excluding TARGET). "
            f"Missing in test: {missing_in_test}; "
            f"missing in train: {missing_in_train}."
        )

    return train_df, test_df


def save_full_feature_dataset(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    output_train_path: str | Path,
    output_test_path: str | Path,
) -> None:
    """Persist the final train/test feature datasets as parquet files.

    Parent directories are created if they do not exist.
    """
    output_train_path = Path(output_train_path)
    output_test_path = Path(output_test_path)
    output_train_path.parent.mkdir(parents=True, exist_ok=True)
    output_test_path.parent.mkdir(parents=True, exist_ok=True)
    train_df.to_parquet(output_train_path, index=False)
    test_df.to_parquet(output_test_path, index=False)


def run_build_full_feature_dataset(
    feature_config_path: str | Path = "configs/features.yaml",
) -> dict[str, Any]:
    """End-to-end entrypoint used by the CLI.

    Loads the three input feature parquet files, builds the final train/test
    datasets, saves them and returns a small summary dictionary.
    """
    config = load_full_feature_dataset_config(feature_config_path)
    dataset_config = config["full_feature_dataset"]

    id_column = dataset_config["id_column"]
    target_column = dataset_config["target_column"]

    application_train_features = load_feature_parquet(
        dataset_config["application_train_features_path"]
    )
    application_test_features = load_feature_parquet(
        dataset_config["application_test_features_path"]
    )
    bureau_features = load_feature_parquet(dataset_config["bureau_features_path"])

    train_df, test_df = build_full_feature_dataset(
        application_train_features,
        application_test_features,
        bureau_features,
        id_column=id_column,
        target_column=target_column,
    )

    output_train_path = dataset_config["output_train_path"]
    output_test_path = dataset_config["output_test_path"]
    save_full_feature_dataset(train_df, test_df, output_train_path, output_test_path)

    feature_count = len(
        [c for c in train_df.columns if c not in (id_column, target_column)]
    )

    return {
        "train_shape": train_df.shape,
        "test_shape": test_df.shape,
        "train_output_path": str(output_train_path),
        "test_output_path": str(output_test_path),
        "feature_count": feature_count,
        "id_column": id_column,
        "target_column": target_column,
    }
