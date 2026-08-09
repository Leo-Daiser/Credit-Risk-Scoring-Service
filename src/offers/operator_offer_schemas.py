from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

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
RISK_BANDS = {"low", "medium", "high", "very_high", "unknown"}
PTI_BANDS = {"low", "moderate", "high", "very_high", "unknown"}
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
RAW_SECRET_URL_PATTERN = re.compile(
    r"(?i)https?://[^\s]*(?:token|secret|api[_-]?key|password)="
)
RATE_DISPLAY_PATTERN = re.compile(r"(?i)(?:ставк|процент|\d(?:[\s.,]\d)?\s*%)")
ALLOWED_CTA_TEXT = {
    "Посмотреть условия",
    "Перейти к предложению",
    "Продолжить у партнёра",
}


class OfferWritable(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider_id: str = "demo"
    provider_offer_id: str | None = Field(default=None, max_length=128)
    bank_id: str = Field(min_length=1, max_length=64)
    product_name: str = Field(min_length=1, max_length=255)
    product_type: str = Field(min_length=1, max_length=64)
    is_active: bool = True
    priority: int = Field(default=50, ge=0, le=100)
    min_amount: float = Field(gt=0, le=100_000_000)
    max_amount: float = Field(gt=0, le=100_000_000)
    min_term_months: int = Field(ge=3, le=360)
    max_term_months: int = Field(ge=3, le=360)
    annual_rate_min: float | None = Field(default=None, ge=0, le=100)
    annual_rate_max: float | None = Field(default=None, ge=0, le=100)
    fee_disclosure: str | None = Field(default=None, max_length=1000)
    insurance_disclosure: str | None = Field(default=None, max_length=1000)
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
    full_cost_range_text: str | None = Field(default=None, max_length=1000)
    compensation_disclosure: str = Field(default="", max_length=1000)
    partner_terms_url: str | None = Field(default=None, max_length=1000)
    main_benefit: str | None = Field(default=None, max_length=255)
    display_warnings: list[str] = Field(default_factory=list, max_length=8)
    cta_text: str = Field(default="Посмотреть условия", max_length=64)
    partner_id: str = Field(min_length=1, max_length=64)
    affiliate_url_template_key: str | None = Field(default=None, max_length=128)
    commission_type: Literal["none", "fixed", "percent"] = "none"
    commission_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    expires_at: datetime | None = None

    @field_validator("provider_id", "bank_id", "product_type", "partner_id")
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

    @field_validator("partner_terms_url")
    @classmethod
    def validate_partner_terms_url(cls, value: str | None) -> str | None:
        if value is None or not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("must be a public HTTPS partner terms URL")
        if parsed.query or parsed.fragment or RAW_SECRET_URL_PATTERN.search(value):
            raise ValueError("must not contain query, fragment, or token material")
        return value

    @field_validator("display_warnings")
    @classmethod
    def validate_display_warnings(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(len(item) > 255 for item in cleaned):
            raise ValueError("display warning is too long")
        return cleaned

    @field_validator("cta_text")
    @classmethod
    def validate_cta_text(cls, value: str) -> str:
        if value not in ALLOWED_CTA_TEXT:
            raise ValueError("must use an approved transparent CTA")
        return value

    @model_validator(mode="after")
    def validate_offer_contract(self) -> OfferWritable:
        if self.max_amount < self.min_amount:
            raise ValueError("max_amount must be greater than or equal to min_amount")
        if self.max_term_months < self.min_term_months:
            raise ValueError("max_term_months must be greater than or equal to min_term_months")
        if (self.annual_rate_min is None) != (self.annual_rate_max is None):
            raise ValueError("both annual rate bounds are required together")
        if (
            self.annual_rate_min is not None
            and self.annual_rate_max is not None
            and self.annual_rate_max < self.annual_rate_min
        ):
            raise ValueError("annual_rate_max must not be lower than annual_rate_min")
        if self.annual_rate_min is not None and not self.full_cost_range_text:
            raise ValueError("rate display requires full_cost_range_text")
        if self.is_active and (
            not self.advertiser_name
            or not self.ad_label_text
            or not self.legal_disclaimer
            or not self.compensation_disclosure
        ):
            raise ValueError("active offer requires advertiser and disclosure fields")
        if self.partner_id != "demo" and self.is_active and not self.affiliate_url_template_key:
            raise ValueError("active real offer requires affiliate_url_template_key")
        if self.partner_id != "demo" and self.is_active and not self.partner_terms_url:
            raise ValueError("active real offer requires partner_terms_url")
        display_copy = " ".join(
            filter(None, (self.product_name, self.main_benefit, self.ad_label_text))
        )
        if self.is_active and RATE_DISPLAY_PATTERN.search(display_copy) and not self.full_cost_range_text:
            raise ValueError("rate display requires full_cost_range_text")
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
            self.full_cost_range_text or "",
            self.compensation_disclosure,
            self.partner_terms_url or "",
            self.main_benefit or "",
            *self.display_warnings,
            self.erid or "",
        ):
            if RAW_SECRET_URL_PATTERN.search(value):
                raise ValueError("raw token-bearing URL is forbidden")
        return self


class OfferPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider_id: str | None = None
    provider_offer_id: str | None = Field(default=None, max_length=128)
    bank_id: str | None = None
    product_name: str | None = None
    product_type: str | None = None
    is_active: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    min_amount: float | None = Field(default=None, gt=0, le=100_000_000)
    max_amount: float | None = Field(default=None, gt=0, le=100_000_000)
    min_term_months: int | None = Field(default=None, ge=3, le=360)
    max_term_months: int | None = Field(default=None, ge=3, le=360)
    annual_rate_min: float | None = Field(default=None, ge=0, le=100)
    annual_rate_max: float | None = Field(default=None, ge=0, le=100)
    fee_disclosure: str | None = Field(default=None, max_length=1000)
    insurance_disclosure: str | None = Field(default=None, max_length=1000)
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
    full_cost_range_text: str | None = Field(default=None, max_length=1000)
    compensation_disclosure: str | None = Field(default=None, max_length=1000)
    partner_terms_url: str | None = Field(default=None, max_length=1000)
    main_benefit: str | None = Field(default=None, max_length=255)
    display_warnings: list[str] | None = None
    cta_text: str | None = Field(default=None, max_length=64)
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
    provider_id: str
    provider_offer_id: str | None
    bank_id: str
    product_name: str
    product_type: str
    is_active: bool
    priority: int
    min_amount: float
    max_amount: float
    min_term_months: int
    max_term_months: int
    annual_rate_min: float | None
    annual_rate_max: float | None
    fee_disclosure: str | None
    insurance_disclosure: str | None
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
    full_cost_range_text: str | None
    compensation_disclosure: str
    partner_terms_url: str | None
    main_benefit: str | None
    display_warnings: list[str]
    cta_text: str
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
