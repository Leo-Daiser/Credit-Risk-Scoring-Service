"""Deterministic local bootstrap for trusted, gitignored ML artifacts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.core.config import Settings, settings
from src.public_profile.service import load_public_profile_bundle
from src.public_profile.training import (
    build_normalized_training_dataset,
    load_public_model_config,
    train_public_profile_model,
)
from src.services.scoring import load_model_bundle


def prepare_local_ml(
    *,
    config: Settings = settings,
    public_config_path: str | Path = "configs/public_profile_model.yaml",
    build_dataset: Callable[[str | Path], dict[str, Any]] = build_normalized_training_dataset,
    train_model: Callable[[str | Path], dict[str, Any]] = train_public_profile_model,
) -> dict[str, Any]:
    """Validate local artifacts and train the public model only from a real source."""
    if config.is_public:
        raise RuntimeError("prepare-local-ml is a local/demo command and is disabled in public mode")

    full_path = Path(config.resolve_model_bundle_path())
    public_path = Path(config.resolve_public_profile_model_path())
    ranker_path = Path(config.offer_ranker_model_path)
    report: dict[str, Any] = {
        "ok": False,
        "full_model": _validate_artifact(full_path, load_model_bundle),
        "public_model": {
            "status": "MISSING",
            "path": str(public_path),
            "version": None,
            "trained": False,
        },
        "offer_ranker": {
            "status": "AVAILABLE" if ranker_path.is_file() else "NOT_CONFIGURED",
            "path": str(ranker_path),
        },
        "source_dataset": None,
        "errors": [],
    }

    if public_path.is_file():
        try:
            bundle = load_public_profile_bundle(public_path)
        except (OSError, TypeError, ValueError) as exc:
            report["public_model"].update(status="INVALID")
            report["errors"].append(f"Public Profile Model is invalid: {exc}")
            return report
        report["public_model"].update(
            status="AVAILABLE",
            version=str(bundle.metadata["model_version"]),
        )
        report["source_dataset"] = str(bundle.metadata.get("training_source") or "unknown")
        report["ok"] = True
        return report

    model_config = load_public_model_config(public_config_path)
    source_path = Path(model_config["source"]["application_train_path"])
    report["source_dataset"] = str(source_path)
    if not source_path.is_file():
        report["errors"].append(
            "Public Profile Model cannot be trained because the configured source "
            f"dataset is missing: {source_path}. Download the legitimate source locally; "
            "do not add it to Git."
        )
        return report

    build_dataset(public_config_path)
    training = train_model(public_config_path)
    trained_path = Path(training["bundle_path"])
    bundle = load_public_profile_bundle(trained_path)
    report["public_model"].update(
        status="TRAINED",
        path=str(trained_path),
        version=str(bundle.metadata["model_version"]),
        trained=True,
    )
    report["source_dataset"] = str(source_path)
    report["ok"] = True
    return report


def _validate_artifact(path: Path, loader: Callable[[Path], Any]) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "MISSING", "path": str(path), "version": None}
    try:
        bundle = loader(path)
    except (OSError, TypeError, ValueError) as exc:
        return {
            "status": "INVALID",
            "path": str(path),
            "version": None,
            "error": str(exc),
        }
    return {
        "status": "AVAILABLE",
        "path": str(path),
        "version": str(bundle.metadata.get("model_version") or "unknown"),
    }
