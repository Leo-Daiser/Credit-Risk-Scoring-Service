import sys

from src.data.load_raw import load_data_config, load_raw_tables
from src.data.validate_schema import validate_raw_tables
from src.db.init_db import init_db
from src.features.application_features import run_build_application_features
from src.features.bureau_features import run_build_bureau_features
from src.features.bureau_features import run_build_bureau_features

DATA_CONFIG_PATH = "configs/data.yaml"
FEATURE_CONFIG_PATH = "configs/features.yaml"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m src.cli <command>")

    command = sys.argv[1]

    if command == "init-db":
        init_db()
        print("Database initialized.")

    elif command == "validate-raw":
        config = load_data_config(DATA_CONFIG_PATH)
        tables = load_raw_tables(DATA_CONFIG_PATH)
        report = validate_raw_tables(tables, config, strict_fk=False)

        print("Raw data validation completed.")
        for table_name, df in tables.items():
            print(f"{table_name}: shape={df.shape}")

        fk_report = report["fk_report"]
        print(
            f"FK report | {fk_report['relationship_name']} | "
            f"orphans={fk_report['orphan_count']} "
            f"({fk_report['orphan_ratio']:.4%})"
        )

        if fk_report["orphan_count"] > 0:
            print("Sample orphan keys:", fk_report["sample_orphans"])

    elif command == "build-application-features":
        summary = run_build_application_features(
            data_config_path=DATA_CONFIG_PATH,
            feature_config_path=FEATURE_CONFIG_PATH,
        )

        print("Application-level features built.")
        print(
            f"Train features: shape={summary['train_shape']} -> {summary['train_path']}"
        )
        print(
            f"Test features:  shape={summary['test_shape']} -> {summary['test_path']}"
        )

    elif command == "build-bureau-features":
        summary = run_build_bureau_features(
            data_config_path=DATA_CONFIG_PATH,
            feature_config_path=FEATURE_CONFIG_PATH,
        )

        print("Bureau features built.")
        print(f"Bureau features: shape={summary['shape']}")
        print(f"Unique applicants: {summary['unique_applicants']}")
        print(f"Feature count: {summary['feature_count']}")
        print(f"Saved to: {summary['output_path']}")

    elif command == "build-bureau-features":
        summary = run_build_bureau_features(
            data_config_path=DATA_CONFIG_PATH,
            feature_config_path=FEATURE_CONFIG_PATH,
        )

        print("Bureau-level features built.")
        print(
            f"Bureau features: shape={summary['bureau_features_shape']} "
            f"-> {summary['bureau_features_path']}"
        )
        print(
            f"Applicants: {summary['n_applicants']} | "
            f"feature columns: {summary['n_feature_columns']}"
        )

    else:
        raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
