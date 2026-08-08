import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.base import Base
from src.db.models import (
    BankOffer,
    BatchScoringJob,
    ModelRegistry,
    OfferClick,
    PartnerPostback,
    ScoringPrediction,
    ScoringRequest,
)


@pytest.fixture()
def audit_engine():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def test_audit_schema_rejects_unregistered_model_version(audit_engine):
    with Session(audit_engine) as session:
        session.add(
            ScoringRequest(
                request_id="orphan-request",
                payload_json={},
                model_version="missing-model",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("probability,risk_band", [(-0.01, "low"), (1.01, "high"), (0.5, "")])
def test_audit_schema_rejects_invalid_prediction(audit_engine, probability, risk_band):
    with Session(audit_engine) as session:
        session.add(
            ModelRegistry(
                model_version="registered-model",
                model_type="test",
                artifact_path="in-memory",
            )
        )
        session.add(
            ScoringRequest(
                request_id="valid-request",
                payload_json={},
                model_version="registered-model",
            )
        )
        session.commit()
        session.add(
            ScoringPrediction(
                request_id="valid-request",
                default_probability=probability,
                risk_band=risk_band,
                top_reason_codes=[],
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_audit_schema_has_model_time_index(audit_engine):
    indexes = inspect(audit_engine).get_indexes("scoring_requests")
    assert any(
        index["name"] == "ix_scoring_requests_model_version_received_at"
        and index["column_names"] == ["model_version", "received_at"]
        for index in indexes
    )


def test_batch_job_schema_has_contract_columns_constraints_and_claim_index(audit_engine):
    inspector = inspect(audit_engine)
    columns = {column["name"]: column for column in inspector.get_columns("batch_scoring_jobs")}
    assert {
        "job_id",
        "input_path",
        "output_path",
        "status",
        "rows_total",
        "rows_processed",
        "model_version",
        "error_message",
        "created_at",
        "started_at",
        "completed_at",
    } <= columns.keys()
    assert columns["job_id"]["nullable"] is False
    assert columns["status"]["nullable"] is False
    assert columns["rows_processed"]["nullable"] is False

    indexes = inspector.get_indexes(BatchScoringJob.__tablename__)
    assert any(
        index["name"] == "ix_batch_scoring_jobs_status_created_at"
        and index["column_names"] == ["status", "created_at"]
        for index in indexes
    )
    unique_constraints = inspector.get_unique_constraints(BatchScoringJob.__tablename__)
    assert any(constraint["column_names"] == ["job_id"] for constraint in unique_constraints)
    check_names = {
        constraint["name"] for constraint in inspector.get_check_constraints("batch_scoring_jobs")
    }
    assert {
        "ck_batch_scoring_jobs_status",
        "ck_batch_scoring_jobs_rows_total_nonnegative",
        "ck_batch_scoring_jobs_rows_processed_nonnegative",
    } <= check_names


def test_commercial_tables_have_idempotency_and_query_indexes(audit_engine):
    inspector = inspect(audit_engine)
    assert {
        "bank_offers",
        "anonymous_sessions",
        "credit_profile_events",
        "offer_impressions",
        "offer_clicks",
        "partner_postbacks",
        "commercial_funnel_events",
    } <= set(inspector.get_table_names())
    click_uniques = inspector.get_unique_constraints(OfferClick.__tablename__)
    assert any(item["column_names"] == ["click_id"] for item in click_uniques)
    postback_uniques = inspector.get_unique_constraints(PartnerPostback.__tablename__)
    assert any(
        item["column_names"] == ["click_id", "status"] for item in postback_uniques
    )
    offer_checks = {
        item["name"] for item in inspector.get_check_constraints(BankOffer.__tablename__)
    }
    assert {"ck_bank_offers_amount", "ck_bank_offers_term", "ck_bank_offers_priority"} <= (
        offer_checks
    )
    postback_checks = {
        item["name"] for item in inspector.get_check_constraints(PartnerPostback.__tablename__)
    }
    assert "ck_partner_postbacks_status" in postback_checks
    impression_columns = {
        item["name"] for item in inspector.get_columns("offer_impressions")
    }
    click_columns = {item["name"] for item in inspector.get_columns("offer_clicks")}
    offer_columns = {item["name"] for item in inspector.get_columns("bank_offers")}
    assert "experiment_variant" in impression_columns
    assert "experiment_variant" in click_columns
    assert {"partner_id", "expires_at"} <= offer_columns
