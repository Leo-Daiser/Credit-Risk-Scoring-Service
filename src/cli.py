"""Command-line entrypoint for the Credit Risk Scoring Service.

Usage:
    python -m src.cli <command>

Supported commands:
    init-db
    validate-raw
    build-application-features
    build-bureau-features
    build-advanced-history-features
    build-full-features
    train-baseline
    train-catboost
    prepare-production-model
    build-public-profile-dataset
    train-public-profile-model
    prepare-local-ml
    batch-score
    monitor-drift
    seed-demo-offers
    build-offer-ranking-dataset
    train-offer-ranker
    evaluate-offer-ranker
    import-offers
    export-offers
    setup-demo
    verify-demo
"""

import argparse
import sys

from src.data.validate_schema import validate_configured_raw_data
from src.db.init_db import init_db
from src.db.session import SessionLocal
from src.features.advanced_history_features import run_build_advanced_history_features
from src.features.application_features import run_build_application_features
from src.features.bureau_features import run_build_bureau_features
from src.features.feature_dataset import run_build_full_feature_dataset
from src.models.prepare_production_model import prepare_production_model
from src.models.train_baseline import train_logistic_regression_baseline
from src.models.train_catboost import train_catboost_challenger
from src.offers.importer import OfferImportValidationError, export_offers, import_offers
from src.offers.repository import OfferRepository
from src.offers.train_offer_ranker import evaluate_offer_ranker, train_offer_ranker
from src.offers.training_dataset import build_offer_ranking_dataset
from src.public_profile.training import (
    build_normalized_training_dataset,
    train_public_profile_model,
)
from src.services.batch import run_batch_scoring
from src.services.demo_setup import setup_demo, verify_demo
from src.services.local_ml import prepare_local_ml
from src.services.monitoring import run_drift_monitoring

DATA_CONFIG_PATH = "configs/data.yaml"
FEATURE_CONFIG_PATH = "configs/features.yaml"
TRAIN_CONFIG_PATH = "configs/train.yaml"
SERVICE_CONFIG_PATH = "configs/service.yaml"
PUBLIC_PROFILE_CONFIG_PATH = "configs/public_profile_model.yaml"

AVAILABLE_COMMANDS = (
    "init-db",
    "validate-raw",
    "build-application-features",
    "build-bureau-features",
    "build-advanced-history-features",
    "build-full-features",
    "train-baseline",
    "train-catboost",
    "prepare-production-model",
    "build-public-profile-dataset",
    "train-public-profile-model",
    "prepare-local-ml",
    "batch-score",
    "monitor-drift",
    "seed-demo-offers",
    "build-offer-ranking-dataset",
    "train-offer-ranker",
    "evaluate-offer-ranker",
    "import-offers",
    "export-offers",
    "setup-demo",
    "verify-demo",
)


def cmd_init_db() -> None:
    """Initialize the database schema."""
    init_db()
    print("Database initialized.")


def cmd_validate_raw() -> None:
    """Load and validate the raw Home Credit tables."""
    report = validate_configured_raw_data(DATA_CONFIG_PATH, strict_fk=False)

    print("Raw data validation completed.")
    for table_name, table_report in report["table_reports"].items():
        print(f"{table_name}: shape=({table_report['rows']}, {table_report['columns']})")

    for fk_report in report["relationship_reports"]:
        print(
            f"FK report | {fk_report['relationship_name']} | "
            f"orphans={fk_report['orphan_count']} "
            f"({fk_report['orphan_ratio']:.4%})"
        )
        if fk_report["orphan_count"] > 0:
            print("Sample orphan keys:", fk_report["sample_orphans"])


def cmd_build_application_features() -> None:
    """Build application-level features (train/test)."""
    summary = run_build_application_features(
        data_config_path=DATA_CONFIG_PATH,
        feature_config_path=FEATURE_CONFIG_PATH,
    )

    print("Application-level features built.")
    print(f"Train features: shape={summary['train_shape']}")
    print(f"Test features:  shape={summary['test_shape']}")
    if "train_path" in summary:
        print(f"Train saved to: {summary['train_path']}")
    if "test_path" in summary:
        print(f"Test saved to:  {summary['test_path']}")


def cmd_build_bureau_features() -> None:
    """Build applicant-level bureau / bureau_balance features."""
    summary = run_build_bureau_features(
        data_config_path=DATA_CONFIG_PATH,
        feature_config_path=FEATURE_CONFIG_PATH,
    )

    print("Bureau features built.")
    print(f"Bureau features: shape={summary['shape']}")
    print(f"Unique applicants: {summary['unique_applicants']}")
    print(f"Feature count: {summary['feature_count']}")
    print(f"Saved to: {summary['output_path']}")


def cmd_build_advanced_history_features() -> None:
    """Build applicant-level previous/POS/installment/credit-card features."""
    summary = run_build_advanced_history_features(
        data_config_path=DATA_CONFIG_PATH,
        feature_config_path=FEATURE_CONFIG_PATH,
    )
    print("Advanced history features built.")
    print(f"Advanced features: shape={summary['shape']}")
    print(f"Unique applicants: {summary['unique_applicants']}")
    print(f"Feature count: {summary['feature_count']}")
    print(f"Saved to: {summary['output_path']}")


def cmd_build_full_features() -> None:
    """Build the final train/test ML feature datasets."""
    summary = run_build_full_feature_dataset(
        feature_config_path=FEATURE_CONFIG_PATH,
    )

    print("Full train/test feature datasets built.")
    print(f"Train features: shape={summary['train_shape']}")
    print(f"Test features:  shape={summary['test_shape']}")
    print(f"Feature count: {summary['feature_count']}")
    print(f"Train saved to: {summary['train_output_path']}")
    print(f"Test saved to:  {summary['test_output_path']}")


def cmd_train_baseline() -> None:
    """Train and persist the Logistic Regression baseline."""
    summary = train_logistic_regression_baseline(
        config_path=TRAIN_CONFIG_PATH,
    )

    print("Logistic Regression baseline trained.")
    print(f"Model type: {summary['model_type']}")
    print(f"Train rows: {summary['train_rows']}")
    print(f"Validation rows: {summary['valid_rows']}")
    print(f"Original feature count: {summary['feature_count']}")
    print(f"Encoded feature count: {summary['encoded_feature_count']}")
    print(f"Numeric feature count: {summary['numeric_feature_count']}")
    print(f"Categorical feature count: {summary['categorical_feature_count']}")
    print(f"ROC-AUC: {summary['roc_auc']:.6f}")
    print(f"PR-AUC: {summary['pr_auc']:.6f}")
    print(f"Best threshold: {summary['best_threshold']}")
    print(
        f"Best threshold metric ({summary['best_threshold_metric']}): "
        f"{summary['best_threshold_metric_value']:.6f}"
    )
    print(f"Convergence warning: {summary['convergence_warning']}")
    print(f"Model saved to: {summary['model_output_path']}")
    print(f"Metrics saved to: {summary['metrics_output_path']}")
    print(f"Evaluation report saved to: {summary['evaluation_report_output_path']}")
    print(f"Feature schema saved to: {summary['feature_schema_output_path']}")


def cmd_prepare_production_model() -> None:
    """Calibrate and package the trained baseline for inference."""
    summary = prepare_production_model(config_path=TRAIN_CONFIG_PATH)
    print("Production model prepared.")
    print(f"Model version: {summary['model_version']}")
    print(f"Acceptance gates: {summary['acceptance_status']}")
    print(f"Decision threshold: {summary['decision_threshold']}")
    print(f"Calibration rows: {summary['calibration_rows']}")
    print(f"Evaluation rows: {summary['evaluation_rows']}")
    print(f"Raw Brier score: {summary['raw_brier_score']:.6f}")
    print(f"Calibrated Brier score: {summary['calibrated_brier_score']:.6f}")
    print(f"Bundle saved to: {summary['bundle_output_path']}")
    print(f"Metadata saved to: {summary['metadata_output_path']}")


def cmd_build_public_profile_dataset() -> None:
    """Map provider-specific source columns into the normalized public schema."""
    summary = build_normalized_training_dataset(PUBLIC_PROFILE_CONFIG_PATH)
    print("Normalized public profile training dataset built.")
    print(f"Rows: {summary['rows']}")
    print(f"Output: {summary['output_path']}")


def cmd_train_public_profile_model() -> None:
    """Train, calibrate, validate, and package the public profile model."""
    summary = train_public_profile_model(PUBLIC_PROFILE_CONFIG_PATH)
    print("Riskline Public Profile Model trained.")
    print(f"Model version: {summary['model_version']}")
    print(f"Selected candidate: {summary['selected_candidate']}")
    print(f"Rows: {summary['rows']}")
    print(f"Acceptance status: {summary['acceptance_status']}")
    print(f"Bundle saved to: {summary['bundle_path']}")


def cmd_prepare_local_ml() -> None:
    """Make local/demo ML readiness explicit and reproducible."""
    report = prepare_local_ml(public_config_path=PUBLIC_PROFILE_CONFIG_PATH)
    print("Local ML preparation report")
    print(
        "Full Credit Risk Model: "
        f"{report['full_model']['status']}"
        + (f" ({report['full_model']['version']})" if report['full_model'].get('version') else "")
    )
    print(
        "Riskline Public Profile Model: "
        f"{report['public_model']['status']}"
        + (f" ({report['public_model']['version']})" if report['public_model'].get('version') else "")
    )
    print(f"Offer Outcome Ranker: {report['offer_ranker']['status']}")
    if report.get("source_dataset"):
        print(f"Configured training source: {report['source_dataset']}")
    for error in report["errors"]:
        print(f"ERROR: {error}")
    if not report["ok"]:
        raise SystemExit("PUBLIC ML INACTIVE: local preparation did not produce a valid model.")


def cmd_train_catboost() -> None:
    """Train and persist the CatBoost challenger."""
    summary = train_catboost_challenger(config_path=TRAIN_CONFIG_PATH)
    print("CatBoost challenger trained.")
    print(f"Train rows: {summary['train_rows']}")
    print(f"Validation rows: {summary['valid_rows']}")
    print(f"Feature count: {summary['feature_count']}")
    print(f"ROC-AUC: {summary['roc_auc']:.6f}")
    print(f"PR-AUC: {summary['pr_auc']:.6f}")
    print(f"Brier score: {summary['brier_score']:.6f}")
    print(f"Best threshold: {summary['best_threshold']}")
    print(f"Model saved to: {summary['model_output_path']}")


def cmd_batch_score() -> None:
    """Score the configured batch input file."""
    summary = run_batch_scoring(config_path=SERVICE_CONFIG_PATH)
    print("Batch scoring completed.")
    print(f"Rows scored: {summary['rows_scored']}")
    print(f"Model version: {summary['model_version']}")
    print(f"Mean default probability: {summary['mean_default_probability']:.6f}")
    print(f"Decline rate: {summary['decline_rate']:.6f}")
    print(f"Saved to: {summary['output_path']}")


def cmd_monitor_drift() -> None:
    """Compare the configured dataset with production reference statistics."""
    report = run_drift_monitoring(config_path=SERVICE_CONFIG_PATH)
    print("Drift monitoring completed.")
    print(f"Status: {report['status']}")
    print(f"Rows analyzed: {report['rows_analyzed']}")
    print(f"Critical features: {report['critical_feature_count']}")
    print(f"Warning features: {report['warning_feature_count']}")
    print(f"Report saved to: {report['output_path']}")


def cmd_seed_demo_offers() -> None:
    """Seed deterministic synthetic offers without real partner claims."""
    with SessionLocal() as session:
        created = OfferRepository(session).seed_demo()
    print(f"Demo offers seeded. Created: {created}")


def cmd_build_offer_ranking_dataset() -> None:
    """Build a point-in-time commercial ranking dataset from normalized events."""
    with SessionLocal() as session:
        report = build_offer_ranking_dataset(session)
    print(f"Offer ranking dataset status: {report['status']}")
    print(f"Rows: {report['rows']}")
    print(f"Output: {report['output_path']}")


def cmd_train_offer_ranker() -> None:
    """Train the optional offer ranker only when the data gate is satisfied."""
    report = train_offer_ranker()
    print(f"Offer ranker status: {report['status']}")
    if report.get("reason"):
        print(f"Reason: {report['reason']}")


def cmd_evaluate_offer_ranker() -> None:
    """Read the latest persisted offer ranker evaluation artifact."""
    report = evaluate_offer_ranker()
    print(f"Offer ranker evaluation status: {report['status']}")


def cmd_import_offers(path: str, *, apply: bool) -> None:
    """Validate or atomically upsert a secret-free offer catalog file."""
    try:
        with SessionLocal() as session:
            report = import_offers(session, path, apply=apply)
    except OfferImportValidationError as exc:
        raise SystemExit(f"Offer import rejected: {exc}") from None
    print(f"Offer import mode: {report.mode}")
    print(f"Rows validated: {report.rows}")
    print(
        f"Created: {report.created}; updated: {report.updated}; "
        f"unchanged: {report.unchanged}"
    )
    for warning in report.warnings:
        print(f"Warning: {warning}")


def cmd_export_offers(path: str) -> None:
    """Export only non-secret catalog fields and environment key references."""
    with SessionLocal() as session:
        rows = export_offers(session, path)
    print(f"Offers exported: {rows}")
    print(f"Output path: {path}")


def cmd_setup_demo(*, with_synthetic_events: bool = False) -> None:
    """Apply migrations and idempotently seed the secret-free demo catalog."""
    report = setup_demo(with_synthetic_events=with_synthetic_events)
    print("Demo setup completed.")
    print(f"Migration previous state: {report['migration_previous_state']}")
    print(f"Offers created: {report['offers_created']}")
    print(f"Active offers: {report['active_offers']}")
    print(f"Synthetic events created: {report['synthetic_events_created']}")
    print("Next: start the API and run python -m src.cli verify-demo")


def cmd_verify_demo() -> None:
    """Fail clearly when deployment prerequisites or repository hygiene are broken."""
    report = verify_demo()
    runtime = report["runtime"]
    print(f"Deployment verification: {'PASS' if report['ok'] else 'FAIL'}")
    print(f"Environment: {runtime['app_env']}")
    print(f"Core API ready: {runtime['core_api_ready']}")
    print(f"Commercial matching ready: {runtime['commercial_matching_ready']}")
    print(f"Matching probe ready: {report['matching_probe_ready']}")
    print(f"Model bundle ready: {runtime['model_bundle_ready']}")
    print(f"Full Credit Risk Model ready: {runtime['full_model_available']}")
    print(f"Public Profile Model ready: {runtime['public_model_available']}")
    print(
        "Public ML status: "
        + ("ACTIVE" if runtime["public_model_available"] else "PUBLIC ML INACTIVE — RULES FALLBACK")
    )
    print(f"Offer ranker ready: {runtime['offer_ranker_available']}")
    print(f"Fallback-only mode: {runtime['fallback_only_mode']}")
    for warning in runtime["warnings"]:
        print(f"Warning: {warning}")
    if not report["ok"]:
        raise SystemExit("Verification failed: " + ", ".join(report["failures"]))


COMMANDS = {
    "init-db": cmd_init_db,
    "validate-raw": cmd_validate_raw,
    "build-application-features": cmd_build_application_features,
    "build-bureau-features": cmd_build_bureau_features,
    "build-advanced-history-features": cmd_build_advanced_history_features,
    "build-full-features": cmd_build_full_features,
    "train-baseline": cmd_train_baseline,
    "train-catboost": cmd_train_catboost,
    "prepare-production-model": cmd_prepare_production_model,
    "build-public-profile-dataset": cmd_build_public_profile_dataset,
    "train-public-profile-model": cmd_train_public_profile_model,
    "prepare-local-ml": cmd_prepare_local_ml,
    "batch-score": cmd_batch_score,
    "monitor-drift": cmd_monitor_drift,
    "seed-demo-offers": cmd_seed_demo_offers,
    "build-offer-ranking-dataset": cmd_build_offer_ranking_dataset,
    "train-offer-ranker": cmd_train_offer_ranker,
    "evaluate-offer-ranker": cmd_evaluate_offer_ranker,
}


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv

    if not args:
        raise SystemExit(
            "Usage: python -m src.cli <command>\n"
            f"Available commands: {', '.join(AVAILABLE_COMMANDS)}"
        )

    command = args[0]
    if command == "import-offers":
        parser = argparse.ArgumentParser(prog="python -m src.cli import-offers")
        parser.add_argument("--path", required=True)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")
        parsed = parser.parse_args(args[1:])
        cmd_import_offers(parsed.path, apply=parsed.apply)
        return
    if command == "export-offers":
        parser = argparse.ArgumentParser(prog="python -m src.cli export-offers")
        parser.add_argument("--path", required=True)
        parsed = parser.parse_args(args[1:])
        cmd_export_offers(parsed.path)
        return
    if command == "setup-demo":
        parser = argparse.ArgumentParser(prog="python -m src.cli setup-demo")
        parser.add_argument("--with-synthetic-events", action="store_true")
        parsed = parser.parse_args(args[1:])
        cmd_setup_demo(with_synthetic_events=parsed.with_synthetic_events)
        return
    if command == "verify-demo":
        parser = argparse.ArgumentParser(prog="python -m src.cli verify-demo")
        parser.parse_args(args[1:])
        cmd_verify_demo()
        return
    handler = COMMANDS.get(command)
    if handler is None:
        raise SystemExit(
            f"Unknown command: {command}\nAvailable commands: {', '.join(AVAILABLE_COMMANDS)}"
        )

    handler()


if __name__ == "__main__":
    main()
