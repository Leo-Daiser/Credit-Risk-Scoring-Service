"""Deployment readiness checks shared by HTTP and operator CLI commands."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.config import Settings, settings
from src.db.migrate import migrations_are_current
from src.offers.partners.registry import load_partner_config
from src.offers.repository import OfferRepository

FORBIDDEN_TRACKED_ROOTS = (
    "data/raw",
    "data/processed",
    "artifacts/models",
    "artifacts/metrics",
    "artifacts/reports",
    "artifacts/uploads",
    "artifacts/predictions",
    "frontend/node_modules",
    "frontend/dist",
    "frontend/.next",
)


def tracked_generated_artifacts(project_root: Path = Path(".")) -> list[str]:
    """List forbidden generated files tracked by Git without reading their contents."""
    result = subprocess.run(
        ["git", "ls-files", "--", *FORBIDDEN_TRACKED_ROOTS, ".env", "frontend/.env"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ["git_tracking_check_failed"]
    return sorted(
        line
        for line in result.stdout.splitlines()
        if line.strip() and not line.replace("\\", "/").endswith("/.gitkeep")
    )


def build_runtime_status(
    session: Session,
    *,
    config: Settings = settings,
    check_migrations: bool = True,
) -> dict[str, Any]:
    warnings: list[str] = []
    db_ready = False
    try:
        session.execute(text("SELECT 1"))
        db_ready = True
    except Exception:
        warnings.append("database_unavailable")

    migrations_ready = False
    if db_ready and check_migrations:
        try:
            migrations_ready = migrations_are_current(config.resolved_database_url)
        except Exception:
            warnings.append("migration_status_unavailable")
    elif db_ready:
        migrations_ready = True

    model_path = Path(config.resolve_model_bundle_path())
    model_bundle_ready = model_path.is_file()
    if not model_bundle_ready:
        warnings.append("model_bundle_unavailable_operator_scoring_disabled")

    offer_catalog_ready = False
    if db_ready:
        try:
            offer_catalog_ready = bool(OfferRepository(session).list_active())
        except Exception:
            warnings.append("offer_catalog_status_unavailable")
    if not offer_catalog_ready:
        warnings.append("offer_catalog_empty")

    partner_config_ready = False
    try:
        load_partner_config(config.partner_config_path)
        partner_config_ready = True
    except ValueError:
        warnings.append("partner_config_invalid_or_missing")

    public_mode_safe = not config.is_public or (
        not config.demo_mode
        and not config.operator_ui_enabled
        and config.public_auth_strict
        and bool(config.database_url)
        and bool(config.api_key and config.api_key.get_secret_value().strip())
        and (
            not config.partner_postbacks_enabled
            or bool(
                config.partner_postback_secret
                and config.partner_postback_secret.get_secret_value().strip()
            )
        )
    )
    if not public_mode_safe:
        warnings.append("public_configuration_unsafe")

    commercial_matching_ready = db_ready and migrations_ready and offer_catalog_ready
    core_api_ready = db_ready and migrations_ready and (
        model_bundle_ready or not config.model_bundle_required
    )
    return {
        "app_env": config.app_env,
        "core_api_ready": core_api_ready,
        "db_ready": db_ready,
        "migrations_ready": migrations_ready,
        "model_bundle_ready": model_bundle_ready,
        "commercial_matching_ready": commercial_matching_ready,
        "offer_catalog_ready": offer_catalog_ready,
        "partner_config_ready": partner_config_ready,
        "worker_configured": config.model_bundle_required,
        "public_mode_safe": public_mode_safe,
        "warnings": sorted(set(warnings)),
    }
