"""Idempotent setup and verification for secret-free demo deployments."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import Settings, settings
from src.core.runtime import build_runtime_status, tracked_generated_artifacts
from src.db.migrate import run_migrations
from src.db.models import CommercialFunnelEvent
from src.db.session import SessionLocal
from src.offers.eligibility import evaluate_offer_eligibility
from src.offers.repository import OfferRepository
from src.offers.schemas import CreditProfileInput
from src.offers.service import build_profile_result
from src.public_profile.service import PublicProfileScoringService

SessionFactory = Callable[[], Session]


def _seed_synthetic_events(session: Session) -> int:
    marker = "setup_demo_synthetic_v1"
    if session.scalar(
        select(CommercialFunnelEvent.id).where(
            CommercialFunnelEvent.event_value == marker
        )
    ):
        return 0
    event_types = (
        "landing_viewed",
        "calculator_used",
        "profile_started",
        "profile_submitted",
        "offers_requested",
        "offers_shown",
    )
    session.add_all(
        CommercialFunnelEvent(
            event_type=event_type,
            event_value=marker,
            experiment_variant="rules_v1",
        )
        for event_type in event_types
    )
    session.commit()
    return len(event_types)


def setup_demo(
    *,
    config: Settings = settings,
    session_factory: SessionFactory = SessionLocal,
    migrate: Callable[[], str] = run_migrations,
    with_synthetic_events: bool = False,
) -> dict[str, Any]:
    if not config.demo_adapter_allowed:
        raise RuntimeError(
            "Demo setup requires DEMO_MODE=true or explicit public safe demo adapter mode."
        )
    migration_state = migrate()
    with session_factory() as session:
        created_offers = OfferRepository(session).seed_demo(config.offer_config_path)
        active_offers = len(OfferRepository(session).list_active())
        synthetic_events = (
            _seed_synthetic_events(session) if with_synthetic_events else 0
        )
    if active_offers == 0:
        raise RuntimeError("Demo offer catalog is empty after setup.")
    return {
        "migration_previous_state": migration_state,
        "offers_created": created_offers,
        "active_offers": active_offers,
        "synthetic_events_created": synthetic_events,
    }


def verify_demo(
    *,
    config: Settings = settings,
    session_factory: SessionFactory = SessionLocal,
    project_root: Path = Path("."),
) -> dict[str, Any]:
    matching_probe_ready = False
    with session_factory() as session:
        status = build_runtime_status(session, config=config)
        if status["offer_catalog_ready"]:
            profile = CreditProfileInput.model_validate(
                {
                    "age_band": "31_45",
                    "income_band": "100k_150k",
                    "employment_type": "employee",
                    "requested_amount_band": "100k_300k",
                    "term_months": 24,
                    "existing_monthly_payments_band": "lt_10k",
                    "credit_history_band": "good",
                    "loan_purpose": "cash",
                    "consent_to_process": True,
                }
            )
            scoring_service = None
            if status["public_model_available"]:
                scoring_service = PublicProfileScoringService.from_path(
                    config.resolve_public_profile_model_path()
                )
            result = build_profile_result(profile, scoring_service=scoring_service)
            matching_probe_ready = any(
                evaluate_offer_eligibility(result, offer).eligible
                for offer in OfferRepository(session).list_active()
            )
    tracked = tracked_generated_artifacts(project_root)
    failures: list[str] = []
    if not status["core_api_ready"]:
        failures.append("core_api_not_ready")
    if not status["partner_config_ready"]:
        failures.append("partner_config_not_ready")
    if config.demo_adapter_allowed and not status["offer_catalog_ready"]:
        failures.append("demo_offer_catalog_empty")
    elif config.demo_adapter_allowed and not matching_probe_ready:
        failures.append("demo_matching_probe_has_no_eligible_offer")
    if config.is_public and not status["public_mode_safe"]:
        failures.append("public_configuration_unsafe")
    if tracked:
        failures.append("forbidden_generated_files_are_tracked")
    return {
        "ok": not failures,
        "runtime": status,
        "matching_probe_ready": matching_probe_ready,
        "tracked_forbidden_files": tracked,
        "failures": failures,
    }
