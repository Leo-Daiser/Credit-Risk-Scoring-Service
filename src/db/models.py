from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ScoringRequest(Base):
    __tablename__ = "scoring_requests"
    __table_args__ = (
        Index("ix_scoring_requests_model_version_received_at", "model_version", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    model_version: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("model_registry.model_version"),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ScoringPrediction(Base):
    __tablename__ = "scoring_predictions"
    __table_args__ = (
        CheckConstraint(
            "default_probability >= 0 AND default_probability <= 1",
            name="ck_scoring_predictions_probability_range",
        ),
        CheckConstraint(
            "length(risk_band) > 0",
            name="ck_scoring_predictions_risk_band_nonempty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("scoring_requests.request_id"), unique=True, nullable=False
    )
    default_probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_band: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decision_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_reason_codes: Mapped[list[dict[str, Any]]] = mapped_column(JSON_TYPE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class FeatureStat(Base):
    __tablename__ = "feature_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_name: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    train_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    train_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    missing_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class BatchScoringJob(Base):
    __tablename__ = "batch_scoring_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_batch_scoring_jobs_status",
        ),
        CheckConstraint(
            "rows_total IS NULL OR rows_total >= 0",
            name="ck_batch_scoring_jobs_rows_total_nonnegative",
        ),
        CheckConstraint(
            "rows_processed >= 0",
            name="ck_batch_scoring_jobs_rows_processed_nonnegative",
        ),
        Index("ix_batch_scoring_jobs_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    input_format: Mapped[str] = mapped_column(String(16), nullable=False)
    id_column: Mapped[str] = mapped_column(String(128), nullable=False)
    input_path: Mapped[str] = mapped_column(Text, nullable=False)
    output_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    rows_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BankOffer(Base):
    __tablename__ = "bank_offers"
    __table_args__ = (
        UniqueConstraint("bank_id", "product_name", name="uq_bank_offers_bank_product"),
        CheckConstraint("min_amount > 0 AND max_amount >= min_amount", name="ck_bank_offers_amount"),
        CheckConstraint(
            "min_term_months >= 3 AND max_term_months >= min_term_months",
            name="ck_bank_offers_term",
        ),
        CheckConstraint("priority >= 0 AND priority <= 100", name="ck_bank_offers_priority"),
        Index("ix_bank_offers_active_priority", "is_active", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[str] = mapped_column(String(64), nullable=False, default="demo")
    bank_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    min_age_band: Mapped[str] = mapped_column(String(32), nullable=False)
    max_age_band: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_age_bands: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    allowed_regions: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    allowed_employment_types: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    allowed_credit_history_bands: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    min_amount: Mapped[float] = mapped_column(Float, nullable=False)
    max_amount: Mapped[float] = mapped_column(Float, nullable=False)
    min_term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    max_term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    min_income_band: Mapped[str] = mapped_column(String(32), nullable=False)
    max_pti_band: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_band_policy: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    affiliate_url_template: Mapped[str] = mapped_column(Text, nullable=False)
    affiliate_url_template_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    advertiser_name: Mapped[str] = mapped_column(String(255), nullable=False)
    erid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ad_label_text: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    full_cost_range_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    compensation_disclosure: Mapped[str] = mapped_column(Text, nullable=False, default="")
    partner_terms_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    main_benefit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_warnings: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)
    cta_text: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Посмотреть условия"
    )
    commission_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    commission_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AnonymousSession(Base):
    __tablename__ = "anonymous_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(128), nullable=True)


class CreditProfileEvent(Base):
    __tablename__ = "credit_profile_events"
    __table_args__ = (
        Index("ix_credit_profile_events_profile_id", "profile_id"),
        Index("ix_credit_profile_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    anonymous_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("anonymous_sessions.id"), nullable=True
    )
    profile_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    risk_band: Mapped[str] = mapped_column(String(32), nullable=False)
    pti_band: Mapped[str] = mapped_column(String(32), nullable=False)
    affordability_band: Mapped[str] = mapped_column(String(32), nullable=False)
    age_band: Mapped[str] = mapped_column(String(32), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    income_band: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_amount_band: Mapped[str] = mapped_column(String(32), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    employment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    credit_history_band: Mapped[str] = mapped_column(String(32), nullable=False)
    loan_purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    data_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class CommercialFunnelEvent(Base):
    """Request-level product event without raw profile or partner payloads."""

    __tablename__ = "commercial_funnel_events"
    __table_args__ = (
        Index("ix_commercial_funnel_events_type_created", "event_type", "created_at"),
        Index("ix_commercial_funnel_events_profile", "profile_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    anonymous_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("anonymous_sessions.id"), nullable=True
    )
    profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("bank_offers.id"), nullable=True)
    click_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    risk_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pti_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    experiment_variant: Mapped[str] = mapped_column(
        String(64), nullable=False, default="rules_v1"
    )
    event_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class OfferImpression(Base):
    __tablename__ = "offer_impressions"
    __table_args__ = (
        Index("ix_offer_impressions_offer_shown", "offer_id", "shown_at"),
        Index("ix_offer_impressions_profile_id", "profile_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    anonymous_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("anonymous_sessions.id"), nullable=True
    )
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("credit_profile_events.profile_id"), nullable=False
    )
    offer_id: Mapped[int] = mapped_column(ForeignKey("bank_offers.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    score_breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    experiment_variant: Mapped[str] = mapped_column(
        String(64), nullable=False, default="rules_v1"
    )
    shown_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class OfferClick(Base):
    __tablename__ = "offer_clicks"
    __table_args__ = (
        Index("ix_offer_clicks_offer_clicked", "offer_id", "clicked_at"),
        Index("ix_offer_clicks_profile_id", "profile_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    click_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    anonymous_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("anonymous_sessions.id"), nullable=True
    )
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("credit_profile_events.profile_id"), nullable=False
    )
    offer_id: Mapped[int] = mapped_column(ForeignKey("bank_offers.id"), nullable=False)
    clicked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    redirect_url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    utm_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(128), nullable=True)
    experiment_variant: Mapped[str] = mapped_column(
        String(64), nullable=False, default="rules_v1"
    )


class PartnerPostback(Base):
    __tablename__ = "partner_postbacks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('application_started', 'application_submitted', 'approved', "
            "'rejected', 'issued', 'cancelled')",
            name="ck_partner_postbacks_status",
        ),
        UniqueConstraint("click_id", "status", name="uq_partner_postback_click_status"),
        Index("ix_partner_postbacks_offer_status", "offer_id", "status"),
        Index("ix_partner_postbacks_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    postback_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    click_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offer_clicks.click_id"), nullable=False
    )
    offer_id: Mapped[int] = mapped_column(ForeignKey("bank_offers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_amount_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    issued_amount_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    commission_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
