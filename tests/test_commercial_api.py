import hmac
from hashlib import sha256

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import get_optional_scoring_service
from src.api.main import app
from src.core.config import settings
from src.db.base import Base
from src.db.models import CreditProfileEvent, OfferClick, OfferImpression, PartnerPostback
from src.db.session import get_db
from src.offers.repository import OfferRepository
from src.offers.schemas import PartnerPostbackRequest
from src.offers.service import canonical_postback_bytes
from src.offers.training_dataset import build_offer_ranking_dataset


@pytest.fixture()
def commercial_client():
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
        assert OfferRepository(session).seed_demo() == 3

    def override_db():
        with testing_session() as session:
            yield session

    old_secret = settings.partner_postback_secret
    settings.partner_postback_secret = SecretStr("postback-test-secret")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_optional_scoring_service] = lambda: None
    try:
        yield TestClient(app), testing_session
    finally:
        settings.partner_postback_secret = old_secret
        app.dependency_overrides.clear()
        engine.dispose()


def profile_payload(consent=True):
    return {
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
        "consent_to_process": consent,
    }


def test_match_requires_consent_and_persists_bands_only(commercial_client):
    client, testing_session = commercial_client
    assert client.post("/v1/offers/match", json={"profile": profile_payload(False)}).status_code == 422
    response = client.post(
        "/v1/offers/match",
        json={
            "profile": profile_payload(),
            "context": {"anonymous_session_id": "browser-session"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile_result"]["risk_score_available"] is False
    assert body["offers"]
    assert all(offer["ad_disclosure"] for offer in body["offers"])
    metrics = client.get("/metrics").text
    assert "credit_risk_offer_impressions_total" in metrics
    assert "credit_risk_offer_click_through_rate" in metrics
    assert "credit_risk_offer_match_requests_total" in metrics
    with testing_session() as session:
        profile = session.scalar(select(CreditProfileEvent))
        assert profile.income_band == "100k_150k"
        assert not hasattr(profile, "requested_amount")
        assert len(session.scalars(select(OfferImpression)).all()) == len(body["offers"])


def test_click_postback_and_dataset_pipeline_is_idempotent(commercial_client, tmp_path):
    client, testing_session = commercial_client
    match = client.post("/v1/offers/match", json={"profile": profile_payload()}).json()
    profile_id = match["profile_result"]["anonymous_profile_id"]
    offer_id = match["offers"][0]["offer_id"]
    click_payload = {"profile_id": profile_id, "idempotency_key": "stable-click-key"}
    first = client.post(f"/v1/offers/{offer_id}/click", json=click_payload)
    second = client.post(f"/v1/offers/{offer_id}/click", json=click_payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["click_id"] == second.json()["click_id"]
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    postback = PartnerPostbackRequest.model_validate(
        {
            "postback_id": "pb-1",
            "click_id": first.json()["click_id"],
            "status": "approved",
            "approved_amount_band": "100k_300k",
        }
    )
    signature = hmac.new(
        b"postback-test-secret", canonical_postback_bytes(postback), sha256
    ).hexdigest()
    headers = {"X-Postback-Signature": signature}
    accepted = client.post("/v1/partner/postback", json=postback.model_dump(mode="json"), headers=headers)
    duplicate = client.post("/v1/partner/postback", json=postback.model_dump(mode="json"), headers=headers)
    assert accepted.json()["duplicate"] is False
    assert duplicate.json()["duplicate"] is True
    assert client.post("/v1/partner/postback", json=postback.model_dump(mode="json")).status_code == 401
    with testing_session() as session:
        assert len(session.scalars(select(OfferClick)).all()) == 1
        assert len(session.scalars(select(PartnerPostback)).all()) == 1
        dataset_path = tmp_path / "ranking.parquet"
        report = build_offer_ranking_dataset(
            session,
            output_path=dataset_path,
            report_path=tmp_path / "report.json",
        )
        frame = pd.read_parquet(dataset_path)
        assert report["rows"] == report["unique_impressions"]
        clicked = frame.loc[frame["offer_id"] == offer_id].iloc[0]
        assert clicked["clicked_flag"] == 1
        assert clicked["approved_flag"] == 1


def test_public_offer_list_does_not_leak_commission_or_affiliate_template(commercial_client):
    client, _ = commercial_client
    response = client.get("/v1/offers")
    assert response.status_code == 200
    item = response.json()[0]
    assert "commission_amount" not in item
    assert "affiliate_url_template" not in item
