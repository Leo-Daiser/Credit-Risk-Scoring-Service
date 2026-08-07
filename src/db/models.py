from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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
