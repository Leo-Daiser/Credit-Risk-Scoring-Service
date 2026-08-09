from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.smoke_public_demo import HttpResult, band_only_profile, run_smoke
from src import cli
from src.core.config import Settings
from src.core.runtime import tracked_generated_artifacts
from src.db.base import Base
from src.services.demo_setup import setup_demo, verify_demo

ROOT = Path(__file__).resolve().parents[1]


def test_artifact_tracking_check_skips_minimal_image_without_git_metadata(tmp_path):
    assert tracked_generated_artifacts(tmp_path) == []


def test_env_example_is_consistent_for_local_compose():
    config = Settings(_env_file=ROOT / ".env.example")
    assert config.app_env == "local"
    assert config.database_url is None
    assert config.resolved_database_url == (
        "postgresql+psycopg2://credit_user:credit_pass@db:5432/credit_risk"
    )


def test_compose_migration_gate_prevents_api_restart_loop():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["migrate"]["restart"] == "no"
    assert services["migrate"]["command"] == ["python", "-m", "src.db.migrate"]
    assert services["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["api"]["command"][0] == "uvicorn"


def test_public_config_rejects_missing_callback_secret():
    with pytest.raises(ValidationError, match="PARTNER_POSTBACK_SECRET"):
        Settings(
            _env_file=None,
            app_env="public",
            demo_mode=False,
            operator_ui_enabled=False,
            public_auth_strict=True,
            database_url="postgresql+psycopg2://user:password@db/database",
            api_key=SecretStr("strong-public-operator-key-123"),
            partner_postbacks_enabled=True,
        )


def test_setup_demo_is_idempotent_on_test_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    config = Settings(_env_file=None, offer_config_path="configs/offers.yaml")

    first = setup_demo(
        config=config,
        session_factory=session_factory,
        migrate=lambda: "empty",
    )
    second = setup_demo(
        config=config,
        session_factory=session_factory,
        migrate=lambda: "managed",
    )

    assert first["offers_created"] > 0
    assert second["offers_created"] == 0
    assert second["active_offers"] == first["active_offers"]


def test_setup_demo_cli_accepts_optional_synthetic_flag(monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(
        cli,
        "setup_demo",
        lambda **kwargs: calls.append(kwargs["with_synthetic_events"])
        or {
            "migration_previous_state": "managed",
            "offers_created": 0,
            "active_offers": 3,
            "synthetic_events_created": 0,
        },
    )
    cli.main(["setup-demo", "--with-synthetic-events"])
    assert calls == [True]


def test_verify_demo_reports_broken_runtime(monkeypatch, tmp_path: Path):
    broken = {
        "app_env": "demo",
        "core_api_ready": False,
        "db_ready": False,
        "migrations_ready": False,
        "model_bundle_ready": False,
        "commercial_matching_ready": False,
        "offer_catalog_ready": False,
        "partner_config_ready": False,
        "worker_configured": False,
        "public_mode_safe": True,
        "warnings": ["database_unavailable"],
    }
    monkeypatch.setattr("src.services.demo_setup.build_runtime_status", lambda *a, **k: broken)
    monkeypatch.setattr("src.services.demo_setup.tracked_generated_artifacts", lambda *a: [])

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return None

    report = verify_demo(
        config=Settings(_env_file=None, app_env="demo"),
        session_factory=SessionContext,
        project_root=tmp_path,
    )
    assert report["ok"] is False
    assert "core_api_not_ready" in report["failures"]
    assert "demo_offer_catalog_empty" in report["failures"]


def test_verify_demo_cli_passes_for_healthy_report(monkeypatch):
    monkeypatch.setattr(
        cli,
        "verify_demo",
        lambda: {
            "ok": True,
            "failures": [],
            "matching_probe_ready": True,
            "runtime": {
                "app_env": "demo",
                "core_api_ready": True,
                "commercial_matching_ready": True,
                "model_bundle_ready": False,
                "warnings": ["model_bundle_unavailable_operator_scoring_disabled"],
            },
        },
    )
    cli.main(["verify-demo"])


class PublicSmokeClient:
    def request(self, method, url, *, payload=None, headers=None):
        path = urlparse(url).path
        if path in {
            "/commercial",
            "/operator",
            "/api/backend/v1/analytics/commercial-summary",
            "/docs",
            "/openapi.json",
            "/metrics",
            "/v1/runtime/status",
            "/v1/partner/postback",
        }:
            return HttpResult(404, {})
        if path == "/v1/profile/score":
            return HttpResult(200, {"risk_band": "unknown"})
        if path == "/v1/offers/match":
            return HttpResult(
                200,
                {
                    "profile_result": {"anonymous_profile_id": "profile-smoke"},
                    "offers": [{"offer_id": 7}],
                },
            )
        if path == "/v1/offers/7/click":
            return HttpResult(200, {"click_id": "click-smoke"})
        return HttpResult(200, {})


class DemoSmokeClient(PublicSmokeClient):
    def request(self, method, url, *, payload=None, headers=None):
        if urlparse(url).path == "/v1/partner/postback":
            if (headers or {}).get("X-Postback-Signature") == "invalid":
                return HttpResult(401, {})
            return HttpResult(200, {"accepted": True})
        return super().request(method, url, payload=payload, headers=headers)


def test_public_smoke_constructs_band_only_requests_and_checks_boundaries():
    assert "requested_amount" not in band_only_profile()
    assert "existing_monthly_payments" not in band_only_profile()
    checks = run_smoke(
        PublicSmokeClient(),
        base_url="http://api.test",
        frontend_url="http://frontend.test",
        mode="public",
    )
    assert "api:click" in checks
    assert "public-boundaries" in checks


def test_demo_smoke_checks_valid_and_invalid_hmac_paths():
    checks = run_smoke(
        DemoSmokeClient(),
        base_url="http://api.test",
        frontend_url="http://frontend.test",
        mode="demo",
        postback_secret="unit-test-demo-secret",
    )
    assert "demo-postback-hmac" in checks
