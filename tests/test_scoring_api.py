import io

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import (
    get_optional_public_profile_scoring_service,
    get_optional_scoring_service,
    get_scoring_service,
)
from src.api.main import app
from src.core.config import settings
from src.db.base import Base
from src.db.models import ModelRegistry, ScoringPrediction, ScoringRequest
from src.db.session import get_db
from src.models.model_bundle import (
    BUNDLE_FORMAT_VERSION,
    REQUIRED_ARTIFACT_INPUTS,
    ModelBundle,
    derive_model_version,
)
from src.models.train_baseline import build_logistic_regression_pipeline
from src.models.train_catboost import build_catboost_pipeline
from src.services.batch_jobs import claim_next_job, process_claimed_job
from src.services.scoring import ScoringService, catboost_reason_codes, linear_reason_codes

TEST_ARTIFACT_INPUTS = {name: "0" * 64 for name in REQUIRED_ARTIFACT_INPUTS}
TEST_MODEL_VERSION = derive_model_version("logistic_regression", TEST_ARTIFACT_INPUTS)


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
            "bundle_format_version": BUNDLE_FORMAT_VERSION,
            "model_version": TEST_MODEL_VERSION,
            "model_type": "logistic_regression",
            "created_at": "2026-08-06T00:00:00+00:00",
            "decision_threshold": 0.5,
            "feature_count": 3,
            "risk_bands": [
                {"name": "low", "upper_bound": 0.25},
                {"name": "medium", "upper_bound": 0.5},
                {"name": "high", "upper_bound": None},
            ],
            "input_contract": {"required_features": [], "min_feature_coverage": 0.0},
            "artifact_inputs": TEST_ARTIFACT_INPUTS,
            "metrics": {"calibrated": {"roc_auc": 0.8, "brier_score": 0.1}},
        },
        feature_schema={
            "feature_names": ["INCOME", "AGE_YEARS", "CONTRACT"],
            "numeric_features": ["INCOME", "AGE_YEARS"],
            "categorical_features": ["CONTRACT"],
        },
        reference_stats={"numeric": {}, "categorical": {}},
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
    app.dependency_overrides[get_optional_scoring_service] = lambda: scoring_service
    app.dependency_overrides[get_optional_public_profile_scoring_service] = lambda: None
    app.dependency_overrides[get_db] = override_db
    original_logging = settings.inference_logging_enabled
    original_required = settings.database_required
    original_api_key = settings.api_key
    settings.inference_logging_enabled = True
    settings.database_required = True
    settings.api_key = SecretStr("operator-test-key")
    try:
        yield TestClient(app, headers={"X-API-Key": "operator-test-key"}), TestingSession
    finally:
        settings.inference_logging_enabled = original_logging
        settings.database_required = original_required
        settings.api_key = original_api_key
        app.dependency_overrides.clear()


def test_model_info_returns_production_metadata(api_client):
    client, _ = api_client
    response = client.get("/model_info")
    assert response.status_code == 200
    assert response.json()["model_version"] == TEST_MODEL_VERSION
    assert response.json()["decision_threshold"] == 0.5
    assert response.json()["confidence_intervals"] == {}


def test_operator_metadata_rejects_missing_and_invalid_key(api_client):
    client, _ = api_client
    assert client.get("/model_info", headers={"X-API-Key": ""}).status_code == 401
    assert client.get("/model_info", headers={"X-API-Key": "wrong"}).status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/feature_schema"),
        ("POST", "/score"),
        ("GET", "/v1/dashboard"),
        ("GET", "/v1/scoring/history"),
        ("GET", "/v1/batch/jobs"),
        ("POST", "/v1/batch/jobs"),
    ],
)
def test_operator_endpoints_fail_closed_without_bff_key(api_client, method, path):
    client, _ = api_client
    assert client.request(method, path, headers={"X-API-Key": ""}).status_code == 401


def test_feature_schema_returns_machine_readable_input_contract(api_client):
    client, _ = api_client
    response = client.get("/feature_schema")
    assert response.status_code == 200
    assert response.json() == {
        "model_version": TEST_MODEL_VERSION,
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
        "status": "degraded",
        "model_version": TEST_MODEL_VERSION,
        "database": "ok",
        "model_bundle_ready": True,
        "full_model_available": True,
        "public_model_available": False,
        "public_model_version": None,
        "offer_ranker_available": False,
        "fallback_only_mode": True,
        "commercial_matching_ready": False,
        "warnings": [
            "public_profile_model_unavailable_rules_fallback_active",
            "offer_catalog_empty",
        ],
    }


def test_readiness_reports_optional_model_bundle_as_unavailable(api_client):
    client, _ = api_client
    app.dependency_overrides[get_optional_scoring_service] = lambda: None
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["model_bundle_ready"] is False
    assert "model_bundle_unavailable_operator_scoring_disabled" in response.json()[
        "warnings"
    ]


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
    assert body["model_version"] == TEST_MODEL_VERSION
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
        assert registries[0].model_version == TEST_MODEL_VERSION


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
        assert client.post(
            "/score", json=payload, headers={"X-API-Key": ""}
        ).status_code == 401
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
    source = scoring_service.bundle
    strict_bundle = ModelBundle(
        model=source.model,
        metadata={
            **source.metadata,
            "input_contract": {
                "required_features": ["INCOME"],
                "min_feature_coverage": 0.75,
            },
        },
        feature_schema=source.feature_schema,
        reference_stats=source.reference_stats,
    )
    strict = ScoringService(strict_bundle)
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


def test_response_echoes_safe_correlation_id(api_client):
    client, _ = api_client
    response = client.get("/health", headers={"X-Correlation-ID": "portfolio-smoke-42"})
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "portfolio-smoke-42"


def test_invalid_correlation_id_is_replaced(api_client):
    client, _ = api_client
    response = client.get("/health", headers={"X-Correlation-ID": "unsafe value"})
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] != "unsafe value"
    assert len(response.headers["X-Correlation-ID"]) == 36


def test_decision_metric_records_only_successful_responses(api_client, monkeypatch):
    client, _ = api_client
    recorded: list[dict] = []
    monkeypatch.setattr(
        "src.api.routes.record_scoring_result", lambda result: recorded.append(result)
    )
    payload = {"request_id": "metric-once", "features": {"INCOME": 100_000}}

    assert client.post("/score", json=payload).status_code == 200
    assert client.post("/score", json=payload).status_code == 409
    assert client.post("/score", json={"features": {"UNKNOWN": 1}}).status_code == 422
    assert len(recorded) == 1


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


def test_portal_dashboard_and_history_use_persisted_decisions(api_client):
    client, _ = api_client
    response = client.post(
        "/score",
        json={
            "request_id": "portal-history-1",
            "features": {"INCOME": 70_000, "AGE_YEARS": 31, "CONTRACT": "cash"},
        },
    )
    assert response.status_code == 200

    history = client.get("/v1/scoring/history").json()
    assert history["total"] == 1
    assert history["items"][0]["request_id"] == "portal-history-1"
    assert history["items"][0]["decision"] == response.json()["decision"]

    dashboard = client.get("/v1/dashboard").json()
    assert dashboard["scoring"]["total"] == 1
    assert dashboard["scoring"]["last_24h"] == 1
    assert dashboard["recent_decisions"][0]["request_id"] == "portal-history-1"


def test_batch_upload_worker_and_result_download(
    api_client,
    scoring_service,
    tmp_path,
    monkeypatch,
):
    client, TestingSession = api_client
    upload_root = tmp_path / "uploads"
    output_root = tmp_path / "predictions"
    monkeypatch.setattr(settings, "batch_storage_dir", str(upload_root))
    monkeypatch.setattr(settings, "batch_output_dir", str(output_root))
    monkeypatch.setattr(settings, "batch_retain_inputs", False)

    csv_payload = (
        "SK_ID_CURR,INCOME,AGE_YEARS,CONTRACT\n"
        "101,70000,31,cash\n"
        "102,130000,52,revolving\n"
    )
    response = client.post(
        "/v1/batch/jobs",
        files={"file": ("applicants.csv", csv_payload, "text/csv")},
        data={"id_column": "SK_ID_CURR"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    input_path = upload_root / f"{job_id}.csv"
    assert input_path.is_file()

    with TestingSession() as session:
        assert claim_next_job(session) == job_id
    process_claimed_job(TestingSession, job_id, scoring_service)

    job = client.get(f"/v1/batch/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["rows_processed"] == 2
    assert not input_path.exists()

    result = client.get(f"/v1/batch/jobs/{job_id}/result")
    assert result.status_code == 200
    scored = pd.read_csv(io.BytesIO(result.content))
    assert list(scored.columns) == [
        "SK_ID_CURR",
        "default_probability",
        "decision",
        "risk_band",
        "model_version",
        "missing_feature_count",
    ]
    assert len(scored) == 2

    template = client.get("/v1/batch/template.csv")
    assert template.status_code == 200
    assert template.text.startswith("SK_ID_CURR,INCOME,AGE_YEARS,CONTRACT")


def test_batch_upload_rejects_invalid_contract_and_cleans_partial_file(
    api_client,
    tmp_path,
    monkeypatch,
):
    client, _ = api_client
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "batch_storage_dir", str(upload_root))
    monkeypatch.setattr(settings, "batch_output_dir", str(tmp_path / "predictions"))
    monkeypatch.setattr(settings, "batch_max_upload_bytes", 16)

    invalid_column = client.post(
        "/v1/batch/jobs",
        files={"file": ("applicants.csv", "SK_ID_CURR\n1\n", "text/csv")},
        data={"id_column": "../customer_id"},
    )
    assert invalid_column.status_code == 422

    oversized = client.post(
        "/v1/batch/jobs",
        files={"file": ("applicants.csv", "SK_ID_CURR,INCOME\n1,70000\n", "text/csv")},
        data={"id_column": "SK_ID_CURR"},
    )
    assert oversized.status_code == 422
    assert "exceeds" in oversized.json()["detail"]
    assert not list(upload_root.glob("*"))


def test_batch_worker_marks_contract_failure_and_retains_input(
    api_client,
    scoring_service,
    tmp_path,
    monkeypatch,
):
    client, TestingSession = api_client
    upload_root = tmp_path / "uploads"
    output_root = tmp_path / "predictions"
    monkeypatch.setattr(settings, "batch_storage_dir", str(upload_root))
    monkeypatch.setattr(settings, "batch_output_dir", str(output_root))

    response = client.post(
        "/v1/batch/jobs",
        files={"file": ("missing-id.csv", "INCOME\n70000\n", "text/csv")},
        data={"id_column": "SK_ID_CURR"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    input_path = upload_root / f"{job_id}.csv"

    with TestingSession() as session:
        assert claim_next_job(session) == job_id
    process_claimed_job(TestingSession, job_id, scoring_service)

    job = client.get(f"/v1/batch/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "failed"
    assert "missing id column" in job.json()["error_message"]
    assert input_path.is_file()
    assert not (output_root / f"{job_id}.csv").exists()
