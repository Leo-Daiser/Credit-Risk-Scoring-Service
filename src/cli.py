import sys

from src.data.load_raw import load_data_config, load_raw_tables
from src.data.validate_schema import validate_raw_tables
from src.db.init_db import init_db
from src.features.application_features import run_build_application_features
from src.features.bureau_features import run_build_bureau_features
from src.features.feature_dataset import run_build_full_feature_dataset
from src.models.train_baseline import train_logistic_regression_baseline

DATA_CONFIG_PATH = "configs/data.yaml"
FEATURE_CONFIG_PATH = "configs/features.yaml"
TRAIN_CONFIG_PATH = "configs/train.yaml"


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

    elif command == "build-full-features":
        summary = run_build_full_feature_dataset(
            feature_config_path=FEATURE_CONFIG_PATH,
        )

        print("Full train/test feature datasets built.")
        print(f"Train features: shape={summary['train_shape']}")
        print(f"Test features:  shape={summary['test_shape']}")
        print(f"Feature count: {summary['feature_count']}")
        print(f"Train saved to: {summary['train_output_path']}")
        print(f"Test saved to:  {summary['test_output_path']}")

    elif command == "train-baseline":
        summary = train_logistic_regression_baseline(
            config_path=TRAIN_CONFIG_PATH,
        )

        print("Logistic Regression baseline trained.")
        print(f"Train rows: {summary['train_rows']}")
        print(f"Validation rows: {summary['valid_rows']}")
        print(f"Feature count: {summary['feature_count']}")
        print(f"Numeric feature count: {summary['numeric_feature_count']}")
        print(f"Categorical feature count: {summary['categorical_feature_count']}")
        print(f"ROC-AUC: {summary['roc_auc']:.6f}")
        print(f"PR-AUC: {summary['pr_auc']:.6f}")
        print(f"Model saved to: {summary['model_output_path']}")
        print(f"Metrics saved to: {summary['metrics_output_path']}")
        print(f"Feature schema saved to: {summary['feature_schema_output_path']}")

    else:
        raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
