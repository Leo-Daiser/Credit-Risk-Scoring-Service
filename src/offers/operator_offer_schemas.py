from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.offers.importer import ENV_KEY_PATTERN
from src.offers.repository import AGE_ORDER

INCOME_BANDS = {
    "lt_50k",
    "50k_100k",
    "100k_150k",
    "150k_250k",
    "gt_250k",
    "unknown",
}
EMPLOYMENT_TYPES = {
    "employee",
    "self_employed",
    "individual_entrepreneur",
    "pensioner",
    "unofficial",
    "unemployed",
    "unknown",
}
CREDIT_HISTORY_BANDS = {
    "good",
    "average",
    "minor_overdues",
    "serious_overdues",
    "no_history",
    "unknown",
}
RISK_BANDS = {"low", "medium", "high", "unknown"}
PTI_BANDS = {"low", "moderate", "high", "very_high", "unknown"}
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
RAW_SECRET_URL_PATTERN = re.compile(
    r"(?i)https?://[^\s]*(?:token|secret|api[_-]?key|password)="
)


class OfferWritable(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bank_id: str = Field(min_length=1, max_length=64)
    product_name: str = Field(min_length=1, max_length=255)
    product_type: str = Field(min_length=1, max_length=64)
    is_active: bool = True
    priority: int = Field(default=50, ge=0, le=100)
    min_amount: float = Field(gt=0, le=100_000_000)
    max_amount: float = Field(gt=0, le=100_000_000)
    min_term_months: int = Field(ge=3, le=360)
    max_term_months: int = Field(ge=3, le=360)
    allowed_age_bands: list[str]
    min_income_band: str = "unknown"
    allowed_regions: list[str] = Field(default_factory=list)
    allowed_employment_types: list[str]
    allowed_credit_history_bands: list[str]
    max_pti_band: str
    risk_band_policy: list[str]
    advertiser_name: str = Field(default="", max_length=255)
    ad_label_text: str = Field(default="", max_length=255)
    erid: str | None = Field(default=None, max_length=128)
    legal_disclaimer: str = Field(default="", max_length=4000)
    partner_id: str = Field(min_length=1, max_length=64)
    affiliate_url_template_key: str | None = Field(default=None, max_length=128)
    commission_type: Literal["none", "fixed", "percent"] = "none"
    commission_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    expires_at: datetime | None = None

    @field_validator("bank_id", "product_type", "partner_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("must be a safe identifier")
        return value

    @field_validator("affiliate_url_template_key")
    @classmethod
    def validate_template_key(cls, value: str | None) -> str | None:
        if value is not None and not ENV_KEY_PATTERN.fullmatch(value):
            raise ValueError("must be an uppercase environment key reference")
        return value

    @field_validator("allowed_age_bands")
    @classmethod
    def validate_age_bands(cls, value: list[str]) -> list[str]:
        cleaned = sorted(set(value), key=AGE_ORDER.index) if value else []
        if not cleaned or any(item not in AGE_ORDER for item in cleaned):
            raise ValueError("must contain supported age bands")
        return cleaned

    @field_validator("min_income_band")
    @classmethod
    def validate_income_band(cls, value: str) -> str:
        if value not in INCOME_BANDS:
            raise ValueError("must be a supported income band")
        return value

    @field_validator("allowed_regions")
    @classmethod
    def validate_regions(cls, value: list[str]) -> list[str]:
        cleaned = sorted({item.strip() for item in value if item.strip()})
        if any(not IDENTIFIER_PATTERN.fullmatch(item) for item in cleaned):
            raise ValueError("must contain safe region identifiers")
        return cleaned

    @field_validator("allowed_employment_types")
    @classmethod
    def validate_employment(cls, value: list[str]) -> list[str]:
        cleaned = sorted(set(value))
        if not cleaned or any(item not in EMPLOYMENT_TYPES for item in cleaned):
            raise ValueError("must contain supported employment types")
        return cleaned

    @field_validator("allowed_credit_history_bands")
    @classmethod
    def validate_credit_history(cls, value: list[str]) -> list[str]:
        cleaned = sorted(set(value))
        if not cleaned or any(item not in CREDIT_HISTORY_BANDS for item in cleaned):
            raise ValueError("must contain supported credit history bands")
        return cleaned

    @field_validator("max_pti_band")
    @classmethod
    def validate_pti(cls, value: str) -> str:
        if value not in PTI_BANDS:
            raise ValueError("must be a supported PTI band")
        return value

    @field_validator("risk_band_policy")
    @classmethod
    def validate_risk_policy(cls, value: list[str]) -> list[str]:
        cleaned = sorted(set(value))
        if not cleaned or any(item not in RISK_BANDS for item in cleaned):
            raise ValueError("must contain supported risk bands")
        return cleaned

    @model_validator(mode="after")
    def validate_offer_contract(self) -> OfferWritable:
        if self.max_amount < self.min_amount:
            raise ValueError("max_amount must be greater than or equal to min_amount")
        if self.max_term_months < self.min_term_months:
            raise ValueError("max_term_months must be greater than or equal to min_term_months")
        if self.is_active and (
            not self.advertiser_name or not self.ad_label_text or not self.legal_disclaimer
        ):
            raise ValueError("active offer requires advertiser and disclosure fields")
        if self.partner_id != "demo" and self.is_active and not self.affiliate_url_template_key:
            raise ValueError("active real offer requires affiliate_url_template_key")
        if self.commission_type == "none" and self.commission_amount not in {None, 0}:
            raise ValueError("commission_amount conflicts with commission_type")
        if self.commission_type != "none" and (
            self.commission_amount is None or self.commission_amount <= 0
        ):
            raise ValueError("commission_amount is required for commercial commission types")
        if self.commission_type == "percent" and (
            self.commission_amount is not None and self.commission_amount > 100
        ):
            raise ValueError("percent commission cannot exceed 100")
        if self.is_active and self.expires_at is not None:
            expires_at = self.expires_at
            if expires_at.tzinfo is not None:
                expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
            if expires_at <= datetime.now(UTC).replace(tzinfo=None):
                raise ValueError("active offer cannot be expired")
        for value in (
            self.product_name,
            self.advertiser_name,
            self.ad_label_text,
            self.legal_disclaimer,
            self.erid or "",
        ):
            if RAW_SECRET_URL_PATTERN.search(value):
                raise ValueError("raw token-bearing URL is forbidden")
        return self


class OfferPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bank_id: str | None = None
    product_name: str | None = None
    product_type: str | None = None
    is_active: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    min_amount: float | None = Field(default=None, gt=0, le=100_000_000)
    max_amount: float | None = Field(default=None, gt=0, le=100_000_000)
    min_term_months: int | None = Field(default=None, ge=3, le=360)
    max_term_months: int | None = Field(default=None, ge=3, le=360)
    allowed_age_bands: list[str] | None = None
    min_income_band: str | None = None
    allowed_regions: list[str] | None = None
    allowed_employment_types: list[str] | None = None
    allowed_credit_history_bands: list[str] | None = None
    max_pti_band: str | None = None
    risk_band_policy: list[str] | None = None
    advertiser_name: str | None = Field(default=None, max_length=255)
    ad_label_text: str | None = Field(default=None, max_length=255)
    erid: str | None = Field(default=None, max_length=128)
    legal_disclaimer: str | None = Field(default=None, max_length=4000)
    partner_id: str | None = None
    affiliate_url_template_key: str | None = Field(default=None, max_length=128)
    commission_type: Literal["none", "fixed", "percent"] | None = None
    commission_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    expires_at: datetime | None = None


class OfferValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OperatorOfferResponse(BaseModel):
    id: int
    bank_id: str
    product_name: str
    product_type: str
    is_active: bool
    priority: int
    min_amount: float
    max_amount: float
    min_term_months: int
    max_term_months: int
    allowed_age_bands: list[str]
    min_income_band: str
    allowed_regions: list[str]
    allowed_employment_types: list[str]
    allowed_credit_history_bands: list[str]
    max_pti_band: str
    risk_band_policy: list[str]
    advertiser_name: str
    ad_label_text: str
    erid: str | None
    legal_disclaimer: str
    partner_id: str
    affiliate_url_template_key: str | None
    commission_type: str
    commission_amount: float | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    validation_status: Literal["valid", "invalid"]
    validation_errors: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    quality_recommendation: str


class OperatorOfferListResponse(BaseModel):
    items: list[OperatorOfferResponse]
    total: int
