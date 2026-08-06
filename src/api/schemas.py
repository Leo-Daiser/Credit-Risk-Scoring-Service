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
    features: dict[str, FeatureValue] = Field(min_length=1, max_length=512)


class ReasonCode(BaseModel):
    code: str
    feature: str
    contribution: float
    direction: Literal["increases_risk"]
    description: str


class ScoreResponse(BaseModel):
    request_id: str
    default_probability: float = Field(ge=0.0, le=1.0)
    decision: Literal["approve", "decline"]
    decision_threshold: float = Field(ge=0.0, le=1.0)
    risk_band: str
    reason_codes: list[ReasonCode]
    model_version: str
    missing_feature_count: int = Field(ge=0)
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


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    model_version: str
    database: Literal["ok"]
