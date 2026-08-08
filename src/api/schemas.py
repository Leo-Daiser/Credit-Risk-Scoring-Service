from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

RequestId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
FeatureString = Annotated[str, StringConstraints(max_length=256)]
FeatureValue = int | float | FeatureString | bool | None


class HealthResponse(BaseModel):
    status: str
    service: str


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    request_id: RequestId | None = None
    features: dict[str, FeatureValue] = Field(min_length=1, max_length=1000)


class ReasonCode(BaseModel):
    code: str
    feature: str
    contribution: float
    direction: Literal["increases_risk"]
    description: str


class InputQuality(BaseModel):
    supplied_feature_count: int = Field(ge=0)
    supplied_feature_coverage: float = Field(ge=0.0, le=1.0)
    missing_feature_count: int = Field(ge=0)
    out_of_range_features: list[str]
    unseen_categorical_features: list[str]
    warnings: list[str]


class ScoreResponse(BaseModel):
    request_id: str
    default_probability: float = Field(ge=0.0, le=1.0)
    decision: Literal["approve", "decline"]
    decision_threshold: float = Field(ge=0.0, le=1.0)
    risk_band: str
    reason_codes: list[ReasonCode]
    model_version: str
    missing_feature_count: int = Field(ge=0)
    input_quality: InputQuality
    latency_ms: float = Field(ge=0.0)
    logging_status: Literal["persisted", "disabled", "failed"]


class ModelInfoResponse(BaseModel):
    model_version: str
    model_type: str
    created_at: str | None
    feature_count: int
    decision_threshold: float
    risk_bands: list[dict[str, Any]]
    metrics: dict[str, float | None]
    confidence_intervals: dict[str, dict[str, float]]
    acceptance_status: str | None


class FeatureSchemaResponse(BaseModel):
    model_version: str
    feature_count: int = Field(ge=1)
    numeric_features: list[str]
    categorical_features: list[str]
    required_features: list[str]
    min_feature_coverage: float = Field(ge=0.0, le=1.0)


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    model_version: str
    database: Literal["ok"]


class BatchJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    original_filename: str
    input_format: Literal["csv", "parquet"]
    id_column: str
    file_size_bytes: int = Field(ge=1)
    status: Literal["queued", "running", "completed", "failed"]
    rows_total: int | None = Field(default=None, ge=0)
    rows_processed: int = Field(ge=0)
    model_version: str | None
    summary_json: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class BatchJobListResponse(BaseModel):
    items: list[BatchJobResponse]
    total: int = Field(ge=0)


class ScoringHistoryItem(BaseModel):
    request_id: str
    received_at: datetime
    default_probability: float = Field(ge=0.0, le=1.0)
    decision: Literal["approve", "decline"] | None
    decision_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_band: str
    model_version: str


class ScoringHistoryResponse(BaseModel):
    items: list[ScoringHistoryItem]
    total: int = Field(ge=0)


class DashboardScoringSummary(BaseModel):
    total: int = Field(ge=0)
    last_24h: int = Field(ge=0)
    approval_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_default_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_bands: dict[str, int]


class DashboardBatchSummary(BaseModel):
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)


class DashboardResponse(BaseModel):
    generated_at: datetime
    model: ModelInfoResponse
    scoring: DashboardScoringSummary
    batches: DashboardBatchSummary
    recent_decisions: list[ScoringHistoryItem]
