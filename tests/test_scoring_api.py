import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import get_scoring_service
from src.api.main import app
from src.core.config import settings
from src.db.base import Base
from src.db.models import ModelRegistry, ScoringPrediction, ScoringRequest
from src.db.session import get_db
from src.models.model_bundle import ModelBundle
from src.models.train_baseline import build_logistic_regression_pipeline
from src.models.train_catboost import build_catboost_pipeline
from src.services.scoring import ScoringService, catboost_reason_codes, linear_reason_codes


@pytest.fixture()
def scoring_service() -> ScoringService:
    rng = np.random.default_rng(8)
    frame = pd.DataFrame(
        {
            "INCOME": rng.normal(100_000, 20_000, 120),
            "AGE_YEARS": rng.integers(20, 70, 120).astype(float),
            "CONTRACT": rng.choice(["cash", "revolving"], 120),
        }
    )
    target = (
        (frame["INCOME"] < 95_000).astype(int) + (frame["CONTRACT"] == "cash").astype(int) >= 1
    ).astype(int)
    pipeline = build_logistic_regression_pipeline(
        ["INCOME", "AGE_YEARS"],
        ["CONTRACT"],
        max_iter=300,
        solver="liblinear",
        n_jobs=None,
    )
    pipeline.fit(frame, target)
    bundle = ModelBundle(
        model=pipeline,
        metadata={
            "model_version": "test-model-v1",
            "model_type": "logistic_regression",
            "created_at": "2026-08-06T00:00:00+00:00",
            "decision_threshold": 0.5,
            "feature_count": 3,
            "risk_bands": [
                {"name": "low", "upper_bound": 0.25},
                {"name": "medium", "upper_bound": 0.5},
                {"name": "high", "upper_bound": None},
            ],
            "metrics": {"calibrated": {"roc_auc": 0.8, "brier_score": 0.1}},
        },
        feature_schema={
            "feature_names": ["INCOME", "AGE_YEARS", "CONTRACT"],
            "numeric_features": ["INCOME", "AGE_YEARS"],
            "categorical_features": ["CONTRACT"],
        },
        reference_stats={},
    )
    return ScoringService(bundle, top_reason_codes=3)


@pytest.fixture()
def api_client(scoring_service):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_scoring_service] = lambda: scoring_service
    app.dependency_overrides[get_db] = override_db
    original_logging = settings.inference_logging_enabled
    original_required = settings.database_required
    settings.inference_logging_enabled = True
    settings.database_required = True
    try:
        yield TestClient(app), TestingSession
    finally:
        settings.inference_logging_enabled = original_logging
        settings.database_required = original_required
        app.dependency_overrides.clear()


def test_model_info_returns_production_metadata(api_client):
    client, _ = api_client
    response = client.get("/model_info")
    assert response.status_code == 200
    assert response.json()["model_version"] == "test-model-v1"
    assert response.json()["decision_threshold"] == 0.5
    assert response.json()["confidence_intervals"] == {}


def test_feature_schema_returns_machine_readable_input_contract(api_client):
    client, _ = api_client
    response = client.get("/feature_schema")
    assert response.status_code == 200
    assert response.json() == {
        "model_version": "test-model-v1",
        "feature_count": 3,
        "numeric_features": ["INCOME", "AGE_YEARS"],
        "categorical_features": ["CONTRACT"],
        "required_features": [],
        "min_feature_coverage": 0.0,
    }


def test_readiness_checks_model_and_database(api_client):
    client, _ = api_client
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "model_version": "test-model-v1",
        "database": "ok",
    }


def test_score_persists_request_and_prediction_atomically(api_client):
    client, TestingSession = api_client
    payload = {
        "request_id": "request-001",
        "features": {"INCOME": 70_000, "AGE_YEARS": 31, "CONTRACT": "cash"},
    }
    response = client.post("/score", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "request-001"
    assert 0.0 <= body["default_probability"] <= 1.0
    assert body["logging_status"] == "persisted"
    assert body["model_version"] == "test-model-v1"
    assert body["input_quality"] == {
        "supplied_feature_count": 3,
        "supplied_feature_coverage": 1.0,
        "missing_feature_count": 0,
        "out_of_range_features": [],
        "unseen_categorical_features": [],
        "warnings": [],
    }

    with TestingSession() as session:
        assert len(session.scalars(select(ScoringRequest)).all()) == 1
        assert len(session.scalars(select(ScoringPrediction)).all()) == 1


def test_distinct_requests_register_model_once(api_client):
    client, TestingSession = api_client
    first = client.post("/score", json={"request_id": "registry-1", "features": {"INCOME": 90_000}})
    second = client.post(
        "/score", json={"request_id": "registry-2", "features": {"INCOME": 110_000}}
    )
    assert first.status_code == 200
    assert second.status_code == 200

    with TestingSession() as session:
        registries = session.scalars(select(ModelRegistry)).all()
        assert len(registries) == 1
        assert registries[0].model_version == "test-model-v1"


def test_score_rejects_unknown_features(api_client):
    client, _ = api_client
    response = client.post("/score", json={"features": {"UNKNOWN": 1}})
    assert response.status_code == 422
    assert "Unknown model features" in response.json()["detail"]


def test_score_rejects_nested_feature_values(api_client):
    client, _ = api_client
    response = client.post("/score", json={"features": {"INCOME": {"value": 1}}})
    assert response.status_code == 422


def test_score_requires_configured_api_key(api_client):
    client, _ = api_client
    original_api_key = settings.api_key
    settings.api_key = SecretStr("test-secret")
    try:
        payload = {"features": {"INCOME": 70_000, "AGE_YEARS": 31, "CONTRACT": "cash"}}
        assert client.post("/score", json=payload).status_code == 401
        response = client.post(
            "/score",
            json=payload,
            headers={"X-API-Key": "test-secret"},
        )
        assert response.status_code == 200
    finally:
        settings.api_key = original_api_key


def test_score_rejects_invalid_numeric_feature(api_client):
    client, _ = api_client
    response = client.post("/score", json={"features": {"INCOME": "not-a-number"}})
    assert response.status_code == 422
    assert "finite numbers" in response.json()["detail"]


def test_scoring_service_enforces_required_features_and_coverage(scoring_service):
    strict = ScoringService(
        scoring_service.bundle,
        min_feature_coverage=0.75,
        required_features=["INCOME"],
    )
    with pytest.raises(ValueError, match="Required model features"):
        strict.score({"AGE_YEARS": 31, "CONTRACT": "cash"})
    with pytest.raises(ValueError, match="Insufficient feature coverage"):
        strict.score({"INCOME": 70_000})


def test_input_quality_reports_domain_deviations(scoring_service):
    scoring_service.bundle.reference_stats = {
        "numeric": {"INCOME": {"min": 50_000, "max": 200_000}},
        "categorical": {"CONTRACT": {"allowed_values": ["cash", "revolving"]}},
    }
    result = scoring_service.score({"INCOME": 300_000, "AGE_YEARS": 31, "CONTRACT": "unknown"})
    quality = result["input_quality"]
    assert quality["out_of_range_features"] == ["INCOME"]
    assert quality["unseen_categorical_features"] == ["CONTRACT"]
    assert set(quality["warnings"]) == {
        "numeric_values_outside_training_range",
        "categorical_values_not_seen_in_training",
    }


def test_metrics_endpoint_exposes_service_metrics(api_client):
    client, _ = api_client
    assert client.get("/health").status_code == 200
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "credit_risk_http_requests_total" in response.text


def test_score_bounds_identifiers_and_categorical_values(api_client):
    client, _ = api_client
    blank_id = client.post(
        "/score",
        json={"request_id": "   ", "features": {"INCOME": 100_000}},
    )
    long_category = client.post(
        "/score",
        json={"features": {"CONTRACT": "x" * 257}},
    )
    assert blank_id.status_code == 422
    assert long_category.status_code == 422


def test_score_returns_conflict_for_reused_request_id(api_client):
    client, _ = api_client
    payload = {"request_id": "same-id", "features": {"INCOME": 100_000}}
    assert client.post("/score", json=payload).status_code == 200
    second = client.post("/score", json=payload)
    assert second.status_code == 409


def test_linear_reason_codes_are_local_positive_contributions(scoring_service):
    frame = scoring_service.bundle.prepare_frame(
        [{"INCOME": 60_000, "AGE_YEARS": 25, "CONTRACT": "cash"}]
    )
    reasons = linear_reason_codes(scoring_service.bundle.model, frame, limit=3)
    assert reasons
    assert all(reason["contribution"] > 0 for reason in reasons)
    assert all(reason["direction"] == "increases_risk" for reason in reasons)


def test_catboost_reason_codes_are_local_positive_contributions():
    frame = pd.DataFrame(
        {
            "INCOME": [40_000, 150_000, 50_000, 160_000, 45_000, 140_000] * 5,
            "CONTRACT": ["cash", "revolving"] * 15,
        }
    )
    target = np.asarray([1, 0, 1, 0, 1, 0] * 5)
    pipeline = build_catboost_pipeline(
        ["INCOME"],
        ["CONTRACT"],
        iterations=20,
        depth=3,
        thread_count=1,
    )
    pipeline.fit(frame, target)
    reasons = catboost_reason_codes(pipeline, frame.iloc[[0]], limit=2)
    assert reasons
    assert all(reason["contribution"] > 0 for reason in reasons)
