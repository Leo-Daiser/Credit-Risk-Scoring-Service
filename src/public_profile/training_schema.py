from __future__ import annotations

from typing import Protocol

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class PublicProfileTrainingRow(BaseModel):
    """Provider-neutral supervised row consumed by public model training."""

    model_config = ConfigDict(extra="forbid")

    profile_row_id: int
    age: float = Field(ge=18, le=100)
    monthly_income: float = Field(gt=0)
    employment_years: float = Field(ge=0, le=65)
    requested_amount: float = Field(gt=0)
    term_months: float = Field(ge=3, le=120)
    calculated_annuity: float = Field(gt=0)
    existing_monthly_payments: float = Field(ge=0)
    credit_income_ratio: float = Field(ge=0)
    annuity_income_ratio: float = Field(ge=0)
    pti: float = Field(ge=0)
    employment_age_ratio: float = Field(ge=0)
    employment_type: str
    target: int = Field(ge=0, le=1)


class PublicTrainingDataAdapter(Protocol):
    source_id: str

    def transform(self, raw: pd.DataFrame) -> pd.DataFrame: ...


def validate_normalized_training_frame(frame: pd.DataFrame) -> None:
    expected = set(PublicProfileTrainingRow.model_fields)
    missing = sorted(expected - set(frame.columns))
    extra = sorted(set(frame.columns) - expected)
    if missing or extra:
        raise ValueError(
            f"Normalized public training schema mismatch: missing={missing}, extra={extra}"
        )
    if frame.empty:
        raise ValueError("Normalized public training dataset is empty")
    if not set(frame["target"].dropna().unique()).issubset({0, 1}):
        raise ValueError("Normalized public training target must be binary")
