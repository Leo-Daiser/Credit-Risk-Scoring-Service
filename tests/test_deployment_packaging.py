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
from src.offers.constraints import (
    PUBLIC_AGE_MAX,
    PUBLIC_AGE_MIN,
    PUBLIC_AMOUNT_MAX,
    PUBLIC_EMPLOYMENT_YEARS_MAX,
    PUBLIC_EXISTING_PAYMENTS_MAX,
    PUBLIC_TERM_MAX_MONTHS,
    PUBLIC_TERM_MIN_MONTHS,
)
from src.services.demo_setup import setup_demo, verify_demo
from src.services.local_ml import prepare_local_ml

ROOT = Path(__file__).resolve().parents[1]


def test_artifact_tracking_check_skips_minimal_image_without_git_metadata(tmp_path):
    assert tracked_generated_artifacts(tmp_path) == []


def test_env_example_is_consistent_for_local_compose(monkeypatch):
    # Pydantic settings deliberately gives process environment precedence over
    # an env file.  CI exports DATABASE_URL for integration tests, so isolate
    # this contract test from the runner before loading .env.example.
    for name in (
        "DATABASE_URL",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    config = Settings(_env_file=ROOT / ".env.example")
    assert config.app_env == "local"
    assert config.database_url is None
    assert config.resolved_database_url == (
        "postgresql+psycopg2://credit_user:credit_pass@db:5432/credit_risk"
    )


def test_frontend_public_limits_match_backend_contract():
    source = (ROOT / "frontend/app/lib/public-profile-constraints.ts").read_text(
        encoding="utf-8"
    )
    expected = {
        "ageMin": PUBLIC_AGE_MIN,
        "ageMax": PUBLIC_AGE_MAX,
        "amountMax": int(PUBLIC_AMOUNT_MAX),
        "termMinMonths": PUBLIC_TERM_MIN_MONTHS,
        "termMaxMonths": PUBLIC_TERM_MAX_MONTHS,
        "employmentYearsMax": int(PUBLIC_EMPLOYMENT_YEARS_MAX),
        "existingPaymentsMax": int(PUBLIC_EXISTING_PAYMENTS_MAX),
    }
    compact = source.replace("_", "")
    for name, value in expected.items():
        assert f"{name}: {value}" in compact


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
                "full_model_available": False,
                "public_model_available": True,
                "offer_ranker_available": False,
                "fallback_only_mode": False,
                "warnings": ["model_bundle_unavailable_operator_scoring_disabled"],
            },
        },
    )
    cli.main(["verify-demo"])


def test_prepare_local_ml_fails_clearly_without_source(tmp_path: Path):
    config_path = tmp_path / "public.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "source": {
                    "application_train_path": str(tmp_path / "missing.csv"),
                    "normalized_output_path": str(tmp_path / "normalized.parquet"),
                },
                "training": {},
                "outputs": {
                    "bundle_path": str(tmp_path / "public.joblib"),
                    "metrics_path": str(tmp_path / "metrics.json"),
                    "feature_schema_path": str(tmp_path / "schema.json"),
                },
                "provenance": {
                    "training_source": "test",
                    "population_limitations": "test",
                },
            }
        ),
        encoding="utf-8",
    )
    config = Settings(
        _env_file=None,
        model_bundle_path=str(tmp_path / "full.joblib"),
        public_profile_model_path=str(tmp_path / "public.joblib"),
        offer_ranker_model_path=str(tmp_path / "ranker.joblib"),
    )

    report = prepare_local_ml(config=config, public_config_path=config_path)

    assert report["ok"] is False
    assert report["public_model"]["status"] == "MISSING"
    assert "missing.csv" in report["errors"][0]


def test_prepare_local_ml_trains_from_configured_real_source(monkeypatch, tmp_path: Path):
    source = tmp_path / "application_train.csv"
    source.write_text("real local source marker", encoding="utf-8")
    bundle_path = tmp_path / "public.joblib"
    config_path = tmp_path / "public.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "source": {
                    "application_train_path": str(source),
                    "normalized_output_path": str(tmp_path / "normalized.parquet"),
                },
                "training": {},
                "outputs": {
                    "bundle_path": str(bundle_path),
                    "metrics_path": str(tmp_path / "metrics.json"),
                    "feature_schema_path": str(tmp_path / "schema.json"),
                },
                "provenance": {
                    "training_source": "legitimate test source",
                    "population_limitations": "test",
                },
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    class Bundle:
        metadata = {"model_version": "public-test-v1"}

    monkeypatch.setattr(
        "src.services.local_ml.load_public_profile_bundle", lambda path: Bundle()
    )
    config = Settings(
        _env_file=None,
        model_bundle_path=str(tmp_path / "full.joblib"),
        public_profile_model_path=str(bundle_path),
        offer_ranker_model_path=str(tmp_path / "ranker.joblib"),
    )
    report = prepare_local_ml(
        config=config,
        public_config_path=config_path,
        build_dataset=lambda path: calls.append("build") or {"rows": 10},
        train_model=lambda path: calls.append("train")
        or {"bundle_path": str(bundle_path)},
    )

    assert calls == ["build", "train"]
    assert report["ok"] is True
    assert report["public_model"]["status"] == "TRAINED"
    assert report["public_model"]["version"] == "public-test-v1"


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
