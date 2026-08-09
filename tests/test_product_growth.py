import hmac
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import (
    get_optional_public_profile_scoring_service,
    get_optional_scoring_service,
)
from src.api.main import app
from src.api.rate_limit import InMemoryRateLimiter, limiter
from src.core.config import Settings, settings
from src.db.base import Base
from src.db.models import BankOffer, CommercialFunnelEvent, OfferClick, OfferImpression
from src.db.session import get_db
from src.offers.analytics import CommercialAnalyticsService
from src.offers.experiments import assign_experiment_variant
from src.offers.partners.base import PartnerPostbackEnvelope
from src.offers.partners.demo_partner import DemoPartnerAdapter
from src.offers.partners.registry import get_partner_adapter
from src.offers.repository import OfferRepository
from src.offers.schemas import PartnerPostbackRequest
from src.offers.segment_analysis import analyze_segment_opportunities
from src.offers.service import canonical_postback_bytes


def growth_profile(**overrides):
    payload = {
        "age_band": "31_45",
        "region": "moscow",
        "income_band": "100k_150k",
        "employment_type": "employee",
        "requested_amount_band": "100k_300k",
        "requested_amount": 250_000,
        "term_months": 24,
        "existing_monthly_payments_band": "zero",
        "existing_monthly_payments": 0,
        "credit_history_band": "good",
        "loan_purpose": "cash",
        "consent_to_process": True,
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def growth_client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with testing_session() as session:
        OfferRepository(session).seed_demo()

    def override_db():
        with testing_session() as session:
            yield session

    old_api_key = settings.api_key
    old_secret = settings.partner_postback_secret
    old_rate_enabled = settings.rate_limit_enabled
    settings.api_key = SecretStr("operator-test-key")
    settings.partner_postback_secret = SecretStr("growth-postback-secret")
    settings.rate_limit_enabled = False
    limiter.reset()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_optional_scoring_service] = lambda: None
    app.dependency_overrides[get_optional_public_profile_scoring_service] = lambda: None
    try:
        yield TestClient(app), testing_session
    finally:
        settings.api_key = old_api_key
        settings.partner_postback_secret = old_secret
        settings.rate_limit_enabled = old_rate_enabled
        limiter.reset()
        app.dependency_overrides.clear()
        engine.dispose()


def operator_headers():
    return {"X-API-Key": "operator-test-key"}


def operator_offer_payload(**overrides):
    payload = {
        "bank_id": "operator-demo-bank",
        "product_name": "Operator Managed Offer",
        "product_type": "cash",
        "is_active": True,
        "priority": 65,
        "min_amount": 50_000,
        "max_amount": 600_000,
        "min_term_months": 6,
        "max_term_months": 60,
        "allowed_age_bands": ["22_30", "31_45", "46_60"],
        "min_income_band": "50k_100k",
        "allowed_regions": [],
        "allowed_employment_types": ["employee", "self_employed"],
        "allowed_credit_history_bands": ["good", "average", "no_history"],
        "max_pti_band": "high",
        "risk_band_policy": ["low", "medium", "unknown"],
        "advertiser_name": "Operator Demo Advertiser",
        "ad_label_text": "Advertising. Operator demo offer.",
        "erid": None,
        "legal_disclaimer": "Preliminary conditions. Final decision is made by the bank.",
        "full_cost_range_text": None,
        "compensation_disclosure": "Service may receive compensation for a referral.",
        "partner_terms_url": None,
        "main_benefit": "Flexible amount and term",
        "display_warnings": [],
        "cta_text": "Посмотреть условия",
        "partner_id": "demo",
        "affiliate_url_template_key": None,
        "commission_type": "none",
        "commission_amount": None,
        "expires_at": None,
    }
    payload.update(overrides)
    return payload


def test_public_profile_and_matching_work_without_operator_key(growth_client):
    client, _ = growth_client
    profile = client.post("/v1/profile/score", json=growth_profile())
    assert profile.status_code == 200
    matched = client.post("/v1/offers/match", json={"profile": growth_profile()})
    assert matched.status_code == 200
    offer_id = matched.json()["offers"][0]["offer_id"]
    click = client.post(
        f"/v1/offers/{offer_id}/click",
        json={"profile_id": matched.json()["profile_result"]["anonymous_profile_id"]},
    )
    assert click.status_code == 200


def test_operator_offer_list_requires_key_and_returns_quality_without_secrets(
    growth_client, monkeypatch
):
    client, _ = growth_client
    monkeypatch.setenv(
        "DEMO_OPERATOR_TEMPLATE",
        "https://private.example/apply?click_id={click_id}&token=never-return",
    )
    created = client.post(
        "/v1/operator/offers",
        headers=operator_headers(),
        json=operator_offer_payload(
            affiliate_url_template_key="DEMO_OPERATOR_TEMPLATE"
        ),
    )
    assert created.status_code == 201
    assert client.get("/v1/operator/offers").status_code == 401
    listed = client.get(
        "/v1/operator/offers?active=true&search=operator-demo",
        headers=operator_headers(),
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    item = listed.json()["items"][0]
    assert item["validation_status"] == "valid"
    assert "demo_only" in item["quality_flags"] or "placeholder_affiliate_url" in item[
        "quality_flags"
    ]
    assert "affiliate_url_template" not in item
    assert "never-return" not in listed.text


def test_operator_offer_create_patch_validate_and_deactivate(growth_client):
    client, testing_session = growth_client
    created = client.post(
        "/v1/operator/offers",
        headers=operator_headers(),
        json=operator_offer_payload(),
    )
    assert created.status_code == 201
    offer_id = created.json()["id"]
    detail = client.get(
        f"/v1/operator/offers/{offer_id}", headers=operator_headers()
    )
    assert detail.status_code == 200
    assert detail.json()["product_name"] == "Operator Managed Offer"

    invalid = client.post(
        f"/v1/operator/offers/{offer_id}/validate",
        headers=operator_headers(),
        json={"max_amount": 10_000},
    )
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False
    assert invalid.json()["errors"] == ["invalid_offer"]

    patched = client.patch(
        f"/v1/operator/offers/{offer_id}",
        headers=operator_headers(),
        json={"product_name": "Edited Operator Offer", "priority": 70},
    )
    assert patched.status_code == 200
    assert patched.json()["product_name"] == "Edited Operator Offer"
    assert patched.json()["priority"] == 70

    deactivated = client.post(
        f"/v1/operator/offers/{offer_id}/deactivate",
        headers=operator_headers(),
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    with testing_session() as session:
        assert session.get(BankOffer, offer_id).is_active is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_amount": 500_000, "max_amount": 100_000},
        {"is_active": True, "ad_label_text": ""},
        {"is_active": True, "compensation_disclosure": ""},
        {
            "main_benefit": "Ставка 10%",
            "full_cost_range_text": None,
        },
        {
            "advertiser_name": "https://partner.example/?token=raw-secret",
        },
        {
            "partner_id": "future_partner",
            "affiliate_url_template_key": None,
        },
    ],
)
def test_operator_offer_rejects_invalid_payload(growth_client, overrides):
    client, _ = growth_client
    response = client.post(
        "/v1/operator/offers",
        headers=operator_headers(),
        json=operator_offer_payload(**overrides),
    )
    assert response.status_code == 422
    assert "raw-secret" not in response.text


def test_operator_offer_rejects_enabled_real_partner_without_secret(
    growth_client, monkeypatch, tmp_path: Path
):
    client, _ = growth_client
    config = tmp_path / "partners.yaml"
    config.write_text(
        "partners:\n  real_operator:\n    adapter: env_template\n    enabled: true\n"
        "    secret_env: REAL_OPERATOR_SECRET\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "partner_config_path", str(config))
    response = client.post(
        "/v1/operator/offers",
        headers=operator_headers(),
        json=operator_offer_payload(
            partner_id="real_operator",
            affiliate_url_template_key="REAL_OPERATOR_AFFILIATE_TEMPLATE",
            partner_terms_url="https://partner.example/terms",
        ),
    )
    assert response.status_code == 422
    assert "partner_secret_environment_missing" in response.text


def test_operator_offer_management_is_not_available_in_public_mode(growth_client):
    client, _ = growth_client
    previous = settings.app_env
    settings.app_env = "public"
    try:
        response = client.get("/v1/operator/offers", headers=operator_headers())
        assert response.status_code == 404
    finally:
        settings.app_env = previous


def test_public_events_accept_only_safe_allowlisted_metadata(growth_client):
    client, testing_session = growth_client
    response = client.post(
        "/v1/analytics/public-event",
        json={
            "event_type": "landing_viewed",
            "page": "landing",
            "anonymous_session_id": "public-session-001",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert client.post(
        "/v1/analytics/public-event",
        json={
            "event_type": "calculator_used",
            "page": "credit_calculator",
            "exact_income": 150_000,
        },
    ).status_code == 422
    assert client.post(
        "/v1/analytics/public-event",
        json={"event_type": "arbitrary_event", "page": "landing"},
    ).status_code == 422
    with testing_session() as session:
        event_row = session.scalar(
            select(CommercialFunnelEvent).where(
                CommercialFunnelEvent.event_type == "landing_viewed"
            )
        )
        assert event_row.event_value == "landing"
        assert "150000" not in str(event_row.__dict__)


def test_empty_analytics_returns_zeros_and_is_operator_protected(growth_client):
    client, _ = growth_client
    assert client.get("/v1/analytics/commercial-summary").status_code == 401
    assert client.get(
        "/v1/analytics/commercial-summary", headers={"X-API-Key": "wrong"}
    ).status_code == 401
    response = client.get(
        "/v1/analytics/commercial-summary?days=7", headers=operator_headers()
    )
    assert response.status_code == 200, response.text
    summary = response.json()["summary"]
    assert summary["total_profile_scores"] == 0
    assert summary["total_offer_impressions"] == 0
    assert summary["ctr_overall"] == 0
    assert summary["epc_proxy"] == 0
    assert summary["recommended_offer_ctr"] == 0
    assert summary["partner_redirect_failures"] == 0
    assert response.json()["time_window"]["days"] == 7


def test_funnel_ctr_postback_revenue_and_public_privacy(growth_client):
    client, testing_session = growth_client
    match = client.post(
        "/v1/offers/match",
        json={
            "profile": growth_profile(),
            "context": {"anonymous_session_id": "growth-session"},
        },
    )
    assert match.status_code == 200
    body = match.json()
    offer = body["offers"][0]
    assert offer["positive_reasons"]
    assert offer["disclosure"]
    assert offer["ad_disclosure"]
    assert offer["compensation_disclosure"]
    assert offer["legal_disclaimer"]
    assert offer["cta_text"] in {
        "Посмотреть условия",
        "Перейти к предложению",
        "Продолжить у партнёра",
    }
    assert "score_breakdown" not in offer
    assert "expected_revenue_proxy" not in offer
    assert "commission" not in str(body).lower()
    assert offer["product_type"]
    assert offer["min_amount"] < offer["max_amount"]
    assert "affiliate_url_template" not in str(body)
    assert "partner_terms_url" not in str(body)
    click = client.post(
        f"/v1/offers/{offer['offer_id']}/click",
        json={"profile_id": body["profile_result"]["anonymous_profile_id"]},
    ).json()
    for index, status in enumerate(("approved", "issued"), start=1):
        postback = PartnerPostbackRequest.model_validate(
            {
                "postback_id": f"growth-pb-{index}",
                "click_id": click["click_id"],
                "status": status,
                "commission_amount": 1250,
            }
        )
        signature = hmac.new(
            b"growth-postback-secret", canonical_postback_bytes(postback), sha256
        ).hexdigest()
        result = client.post(
            "/v1/partner/postback",
            json=postback.model_dump(mode="json"),
            headers={"X-Postback-Signature": signature},
        )
        assert result.status_code == 200
    analytics = client.get(
        "/v1/analytics/commercial-summary", headers=operator_headers()
    ).json()
    assert analytics["summary"]["total_match_requests"] == 1
    assert analytics["summary"]["total_offer_clicks"] == 1
    assert analytics["summary"]["ctr_overall"] == pytest.approx(
        1 / analytics["summary"]["total_offer_impressions"]
    )
    assert analytics["summary"]["postback_conversion_rate"] == 1
    assert analytics["summary"]["approval_rate"] == 1
    assert analytics["summary"]["issued_rate"] == 1
    assert analytics["summary"]["estimated_revenue"] == 1250
    assert analytics["summary"]["epc_proxy"] == 1250
    assert analytics["summary"]["recommended_offer_ctr"] == 1
    assert analytics["summary"]["top_card_ctr"] == 1
    assert analytics["summary"]["partner_redirect_failures"] == 0
    assert analytics["summary"]["public_event_counts"]["profile_submitted"] == 1
    assert analytics["summary"]["public_event_counts"]["result_viewed"] == 1
    assert analytics["summary"]["public_event_counts"]["offer_card_viewed"] >= 1
    assert "payload" not in str(analytics).lower()
    with testing_session() as session:
        assert session.scalar(select(OfferImpression)).experiment_variant == "rules_v1"
        assert session.scalar(select(OfferClick)).experiment_variant == "rules_v1"


def test_no_eligible_offer_event_and_safe_suggestions(growth_client):
    client, testing_session = growth_client
    response = client.post(
        "/v1/offers/match",
        json={
            "profile": growth_profile(
                employment_type="unemployed",
                credit_history_band="serious_overdues",
                requested_amount_band="gt_1_5m",
                requested_amount=2_000_000,
            )
        },
        headers=operator_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["no_eligible_offers"] is True
    assert body["offers"] == []
    assert body["suggestions"]
    assert "отказ" not in body["user_explanation"].lower()
    assert "плох" not in body["user_explanation"].lower()
    with testing_session() as session:
        events = list(
            session.scalars(
                select(CommercialFunnelEvent).where(
                    CommercialFunnelEvent.event_type == "no_eligible_offers"
                )
            )
        )
        assert len(events) == 1
        summary = CommercialAnalyticsService(session).summary(days=30).summary
        assert summary.no_eligible_offers_rate == 1
        assert summary.public_event_counts["no_eligible_offers_viewed"] == 1


def test_quality_report_flags_demo_copy_and_keeps_inactive_visible(growth_client):
    client, testing_session = growth_client
    with testing_session() as session:
        first = session.get(BankOffer, 1)
        first.advertiser_name = ""
        first.ad_label_text = ""
        second = session.get(BankOffer, 2)
        second.is_active = False
        session.commit()
    report = client.get("/v1/offers/quality-report", headers=operator_headers())
    assert report.status_code == 200
    items = {item["offer_id"]: item for item in report.json()["offers"]}
    assert "missing_advertiser_name" in items[1]["quality_flags"]
    assert "missing_disclosure" in items[1]["quality_flags"]
    assert "placeholder_affiliate_url" in items[1]["quality_flags"]
    assert "expected_revenue_proxy" in items[1]
    assert items[2]["status"] == "inactive"
    managed = client.get("/v1/operator/offers", headers=operator_headers())
    assert managed.status_code == 200
    managed_items = {item["id"]: item for item in managed.json()["items"]}
    assert managed_items[1]["validation_status"] == "invalid"
    assert "missing_disclosure" in managed_items[1]["quality_flags"]
    active_ids = {
        item["id"]
        for item in client.get("/v1/offers", headers=operator_headers()).json()
    }
    assert 2 not in active_ids


def test_segment_opportunity_detects_and_orders_underserved_demand(growth_client):
    client, testing_session = growth_client
    for _ in range(2):
        client.post(
            "/v1/offers/match",
            json={
                "profile": growth_profile(
                    employment_type="unemployed",
                    credit_history_band="serious_overdues",
                )
            },
            headers=operator_headers(),
        )
    with testing_session() as session:
        result = analyze_segment_opportunities(session, days=30)
    assert result.opportunities
    assert result.opportunities[0].requests >= result.opportunities[-1].requests
    serious = next(
        item
        for item in result.opportunities
        if item.segment_key == "credit_history_band"
        and item.segment_value == "serious_overdues"
    )
    assert serious.eligible_offer_rate == 0
    assert serious.recommendation == "add_bad_credit_history_offer"
    serialized = result.model_dump()
    assert "requested_amount" not in serialized
    assert "term_months" not in serialized


def test_demo_partner_url_signature_normalization_and_missing_config(growth_client, tmp_path):
    _, testing_session = growth_client
    adapter = DemoPartnerAdapter("adapter-secret")
    with testing_session() as session:
        offer = session.get(BankOffer, 1)
        url = adapter.build_affiliate_url(
            offer, "click-123", {"utm_source": "portfolio"}
        )
    assert "click_id=click-123" in url
    assert "adapter-secret" not in url
    payload = {
        "postback_id": "normalized-1",
        "partner_id": "demo",
        "click_id": "click-123",
        "status": "APPROVED",
    }
    normalized = adapter.normalize_postback(payload)
    assert normalized.status == "approved"
    assert adapter.verify_postback(PartnerPostbackEnvelope(payload=payload, signature="bad")) is False
    with pytest.raises(ValueError, match="not found"):
        get_partner_adapter("demo", config_path=tmp_path / "missing.yaml")


def test_experiment_assignment_is_deterministic_and_invalid_config_falls_back():
    config = {
        "enabled": True,
        "salt": "test",
        "traffic_split": {
            "rules_v1": 0.5,
            "rules_revenue_weighted_v1": 0.5,
        },
    }
    assert assign_experiment_variant("same-session", config) == assign_experiment_variant(
        "same-session", config
    )
    variants = {
        assign_experiment_variant(f"session-{index}", config) for index in range(200)
    }
    assert variants == {"rules_v1", "rules_revenue_weighted_v1"}
    revenue_weighted = sum(
        assign_experiment_variant(f"session-{index}", config)
        == "rules_revenue_weighted_v1"
        for index in range(200)
    )
    assert 70 <= revenue_weighted <= 130
    invalid = {"enabled": True, "traffic_split": {"unknown": 1.0}}
    assert assign_experiment_variant("session", invalid) == "rules_v1"
    assert assign_experiment_variant("session", {"enabled": False}) == "rules_v1"


def test_in_memory_rate_limiter_allows_then_returns_clear_429():
    now = [0.0]
    local_limiter = InMemoryRateLimiter(clock=lambda: now[0])
    assert local_limiter.check("offer_match", "client", 2, 60) == 1
    assert local_limiter.check("offer_match", "client", 2, 60) == 0
    with pytest.raises(Exception) as exc_info:
        local_limiter.check("offer_match", "client", 2, 60)
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "60"
    now[0] = 61
    assert local_limiter.check("offer_match", "client", 2, 60) == 1


def test_match_endpoint_rate_limit_and_invalid_postback_attempt_tracking(growth_client):
    client, testing_session = growth_client
    old_enabled = settings.rate_limit_enabled
    old_match = settings.rate_limit_offer_match
    old_click = settings.rate_limit_offer_click
    old_invalid = settings.rate_limit_invalid_postback
    settings.rate_limit_enabled = True
    settings.rate_limit_offer_match = 1
    settings.rate_limit_offer_click = 1
    settings.rate_limit_invalid_postback = 1
    limiter.reset()
    try:
        first = client.post(
            "/v1/offers/match",
            json={"profile": growth_profile()},
            headers=operator_headers(),
        )
        second = client.post(
            "/v1/offers/match",
            json={"profile": growth_profile()},
            headers=operator_headers(),
        )
        assert first.status_code == 200
        assert second.status_code == 429
        assert second.headers["Retry-After"]
        matched = first.json()
        click_path = f"/v1/offers/{matched['offers'][0]['offer_id']}/click"
        click_payload = {"profile_id": matched["profile_result"]["anonymous_profile_id"]}
        assert client.post(click_path, json=click_payload, headers=operator_headers()).status_code == 200
        assert client.post(click_path, json=click_payload, headers=operator_headers()).status_code == 429
        invalid_payload = {
            "postback_id": "invalid-pb",
            "click_id": "00000000-0000-0000-0000-000000000000",
            "status": "approved",
        }
        assert client.post("/v1/partner/postback", json=invalid_payload).status_code == 401
        assert client.post("/v1/partner/postback", json=invalid_payload).status_code == 429
        with testing_session() as session:
            attempts = list(
                session.scalars(
                    select(CommercialFunnelEvent).where(
                        CommercialFunnelEvent.event_type == "partner_postback_received"
                    )
                )
            )
            assert attempts and attempts[0].event_value == "invalid"
    finally:
        settings.rate_limit_enabled = old_enabled
        settings.rate_limit_offer_match = old_match
        settings.rate_limit_offer_click = old_click
        settings.rate_limit_invalid_postback = old_invalid
        limiter.reset()


def test_safe_configuration_validation():
    defaults = Settings(_env_file=None)
    assert defaults.offer_ranker_mode == "rules"
    assert defaults.real_partner_enabled is False
    assert defaults.app_env == "local"
    assert defaults.operator_ui_enabled is True
    with pytest.raises(ValidationError, match="REAL_PARTNER_SECRET"):
        Settings(_env_file=None, real_partner_enabled=True)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, offer_ranker_mode="commission_only")
    with pytest.raises(ValidationError, match="DEMO_MODE"):
        Settings(_env_file=None, app_env="public")
    with pytest.raises(ValidationError, match="OPERATOR_UI_ENABLED"):
        Settings(
            _env_file=None,
            app_env="public",
            demo_mode=False,
            public_auth_strict=True,
            api_key=SecretStr("deployment-operator-key-with-entropy"),
        )
    with pytest.raises(ValidationError, match="PUBLIC_AUTH_STRICT"):
        Settings(
            _env_file=None,
            app_env="public",
            demo_mode=False,
            operator_ui_enabled=False,
            api_key=SecretStr("deployment-operator-key-with-entropy"),
        )
    with pytest.raises(ValidationError, match="API_KEY"):
        Settings(
            _env_file=None,
            app_env="public",
            demo_mode=False,
            operator_ui_enabled=False,
            public_auth_strict=True,
            api_key=None,
        )
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(
            _env_file=None,
            app_env="public",
            demo_mode=False,
            operator_ui_enabled=False,
            public_auth_strict=True,
            api_key=SecretStr("change-me"),
        )
    public = Settings(
        _env_file=None,
        app_env="public",
        demo_mode=False,
        operator_ui_enabled=False,
        public_auth_strict=True,
        api_key=SecretStr("deployment-operator-key-with-entropy"),
        database_url="postgresql+psycopg2://user:password@db/database",
        partner_postbacks_enabled=False,
    )
    assert public.is_public is True


def test_public_mode_blocks_demo_partner_and_demo_catalog(growth_client):
    client, _ = growth_client
    old_env = settings.app_env
    settings.app_env = "public"
    try:
        assert client.get("/v1/offers", headers=operator_headers()).status_code == 404
        assert client.get("/v1/runtime/status", headers=operator_headers()).status_code == 404
        payload = PartnerPostbackRequest.model_validate(
            {
                "postback_id": "public-demo-postback",
                "click_id": "00000000-0000-0000-0000-000000000000",
                "status": "approved",
            }
        )
        signature = hmac.new(
            b"growth-postback-secret", canonical_postback_bytes(payload), sha256
        ).hexdigest()
        response = client.post(
            "/v1/partner/postback",
            json=payload.model_dump(mode="json"),
            headers={"X-Postback-Signature": signature},
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Partner unavailable."}
    finally:
        settings.app_env = old_env
