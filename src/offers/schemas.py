from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgeBand(StrEnum):
    AGE_18_21 = "18_21"
    AGE_22_30 = "22_30"
    AGE_31_45 = "31_45"
    AGE_46_60 = "46_60"
    AGE_60_PLUS = "60_plus"


class IncomeBand(StrEnum):
    LT_50K = "lt_50k"
    FROM_50K_TO_100K = "50k_100k"
    FROM_100K_TO_150K = "100k_150k"
    FROM_150K_TO_250K = "150k_250k"
    GT_250K = "gt_250k"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    EMPLOYEE = "employee"
    SELF_EMPLOYED = "self_employed"
    INDIVIDUAL_ENTREPRENEUR = "individual_entrepreneur"
    PENSIONER = "pensioner"
    UNOFFICIAL = "unofficial"
    UNEMPLOYED = "unemployed"
    UNKNOWN = "unknown"


class AmountBand(StrEnum):
    LT_100K = "lt_100k"
    FROM_100K_TO_300K = "100k_300k"
    FROM_300K_TO_700K = "300k_700k"
    FROM_700K_TO_1_5M = "700k_1_5m"
    GT_1_5M = "gt_1_5m"


class PaymentsBand(StrEnum):
    ZERO = "zero"
    LT_10K = "lt_10k"
    FROM_10K_TO_30K = "10k_30k"
    FROM_30K_TO_60K = "30k_60k"
    GT_60K = "gt_60k"
    UNKNOWN = "unknown"


class CreditHistoryBand(StrEnum):
    GOOD = "good"
    AVERAGE = "average"
    MINOR_OVERDUES = "minor_overdues"
    SERIOUS_OVERDUES = "serious_overdues"
    NO_HISTORY = "no_history"
    UNKNOWN = "unknown"


class LoanPurpose(StrEnum):
    CASH = "cash"
    REFINANCE = "refinance"
    CAR = "car"
    REPAIR = "repair"
    EDUCATION = "education"
    MEDICAL = "medical"
    OTHER = "other"


class PtiBand(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
    UNKNOWN = "unknown"


class AffordabilityBand(StrEnum):
    COMFORTABLE = "comfortable"
    MANAGEABLE = "manageable"
    STRETCHED = "stretched"
    UNAFFORDABLE = "unaffordable"
    UNKNOWN = "unknown"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    BASIC = "basic"
    MEDIUM = "medium"
    HIGH = "high"


class CreditProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_band: AgeBand
    region: str | None = Field(default=None, min_length=1, max_length=64)
    income_band: IncomeBand
    employment_type: EmploymentType
    requested_amount_band: AmountBand
    requested_amount: float | None = Field(default=None, gt=0, le=10_000_000)
    term_months: int = Field(ge=3, le=120)
    existing_monthly_payments_band: PaymentsBand
    existing_monthly_payments: float | None = Field(default=None, ge=0, le=2_000_000)
    credit_history_band: CreditHistoryBand
    loan_purpose: LoanPurpose
    consent_to_process: bool
    consent_to_ad_personalization: bool = False

    @model_validator(mode="after")
    def validate_consent(self) -> CreditProfileInput:
        if not self.consent_to_process:
            raise ValueError("consent_to_process must be true for server-side matching")
        amount_ranges = {
            AmountBand.LT_100K: (0, 100_000),
            AmountBand.FROM_100K_TO_300K: (100_000, 300_000),
            AmountBand.FROM_300K_TO_700K: (300_000, 700_000),
            AmountBand.FROM_700K_TO_1_5M: (700_000, 1_500_000),
            AmountBand.GT_1_5M: (1_500_000, 10_000_000),
        }
        if self.requested_amount is not None:
            lower, upper = amount_ranges[self.requested_amount_band]
            if not lower <= self.requested_amount <= upper:
                raise ValueError("requested_amount does not match requested_amount_band")
        payment_ranges = {
            PaymentsBand.ZERO: (0, 0),
            PaymentsBand.LT_10K: (0, 10_000),
            PaymentsBand.FROM_10K_TO_30K: (10_000, 30_000),
            PaymentsBand.FROM_30K_TO_60K: (30_000, 60_000),
            PaymentsBand.GT_60K: (60_000, 2_000_000),
        }
        if self.existing_monthly_payments is not None:
            if self.existing_monthly_payments_band is PaymentsBand.UNKNOWN:
                raise ValueError("exact payments cannot be supplied with an unknown band")
            lower, upper = payment_ranges[self.existing_monthly_payments_band]
            if not lower <= self.existing_monthly_payments <= upper:
                raise ValueError(
                    "existing_monthly_payments does not match its selected band"
                )
        return self


class ProfileBands(BaseModel):
    age_band: AgeBand
    region: str | None = None
    income_band: IncomeBand
    employment_type: EmploymentType
    requested_amount_band: AmountBand
    term_months: int
    existing_monthly_payments_band: PaymentsBand
    credit_history_band: CreditHistoryBand
    loan_purpose: LoanPurpose


class CreditProfileResult(BaseModel):
    anonymous_profile_id: str
    risk_band: str
    risk_score_available: bool
    risk_score: float | None = Field(default=None, ge=0, le=1)
    risk_model_version: str | None = None
    affordability_band: AffordabilityBand
    estimated_monthly_payment: float | None = Field(default=None, ge=0)
    pti_value: float | None = Field(default=None, ge=0)
    pti_band: PtiBand
    data_coverage: float = Field(ge=0, le=1)
    confidence_level: ConfidenceLevel
    warnings: list[str]
    disclaimers: list[str]
    profile_bands: ProfileBands


class OfferPublic(BaseModel):
    id: int
    bank_id: str
    product_name: str
    product_type: str
    advertiser_name: str
    min_amount: float
    max_amount: float
    min_term_months: int
    max_term_months: int
    ad_label_text: str
    legal_disclaimer: str

    model_config = ConfigDict(from_attributes=True)


class OfferEligibilityResult(BaseModel):
    offer_id: int
    eligible: bool
    reasons: list[str]
    blocking_reasons: list[str]
    soft_warnings: list[str]
    matched_rules: dict[str, Any]


class RankedOffer(BaseModel):
    offer_id: int
    rank: int
    bank_id: str
    product_name: str
    advertiser_name: str
    final_score: float = Field(ge=0, le=1)
    score_breakdown: dict[str, float]
    match_reasons: list[str]
    warnings: list[str]
    ad_disclosure: str
    redirect_url: str
    revenue_estimate_source: str
    revenue_estimate_confidence: str
    experiment_variant: str = "rules_v1"


class RankedOfferPublic(BaseModel):
    offer_id: int
    rank: int
    bank_id: str
    product_name: str
    product_type: str
    advertiser_name: str
    is_demo: bool = False
    min_amount: float
    max_amount: float
    min_term_months: int
    max_term_months: int
    positive_reasons: list[str]
    warnings: list[str]
    disclosure: str
    ad_disclosure: str
    confidence_level: ConfidenceLevel
    main_benefit: str | None = None
    full_cost_range_text: str | None = None
    compensation_disclosure: str
    legal_disclaimer: str
    cta_text: str
    redirect_url: str


PublicEventType = Literal[
    "landing_viewed",
    "calculator_used",
    "calculator_continue_clicked",
]


class PublicAnalyticsEventRequest(BaseModel):
    """Allowlisted public product event without arbitrary or financial payloads."""

    model_config = ConfigDict(extra="forbid")

    event_type: PublicEventType
    anonymous_session_id: str | None = Field(default=None, min_length=8, max_length=128)
    page: Literal["landing", "credit_calculator"]


class PublicAnalyticsEventResponse(BaseModel):
    accepted: bool = True


class MatchContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anonymous_session_id: str | None = Field(default=None, max_length=128)
    source: str | None = Field(default=None, max_length=64)
    utm_source: str | None = Field(default=None, max_length=128)
    utm_medium: str | None = Field(default=None, max_length=128)
    utm_campaign: str | None = Field(default=None, max_length=128)


class OfferMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: CreditProfileInput
    limit: int = Field(default=5, ge=1, le=20)
    context: MatchContext | None = None


class OfferMatchResponse(BaseModel):
    profile_result: CreditProfileResult
    offers: list[RankedOfferPublic]
    disclaimers: list[str]
    ad_disclosure_required: bool = True
    no_eligible_offers: bool = False
    user_explanation: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    why_not_reasons: list[str] = Field(default_factory=list)


class ClickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=36)
    anonymous_session_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    utm_source: str | None = Field(default=None, max_length=128)
    utm_medium: str | None = Field(default=None, max_length=128)
    utm_campaign: str | None = Field(default=None, max_length=128)


class ClickResponse(BaseModel):
    click_id: str
    redirect_url: str
    duplicate: bool = False


class PostbackStatus(StrEnum):
    APPLICATION_STARTED = "application_started"
    APPLICATION_SUBMITTED = "application_submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    ISSUED = "issued"
    CANCELLED = "cancelled"


class PartnerPostbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    postback_id: str = Field(min_length=1, max_length=128)
    partner_id: str = Field(default="demo", min_length=1, max_length=64)
    click_id: str = Field(min_length=1, max_length=36)
    status: PostbackStatus
    approved_amount_band: AmountBand | None = None
    issued_amount_band: AmountBand | None = None
    commission_amount: float | None = Field(default=None, ge=0, le=100_000_000)


class PartnerPostbackResponse(BaseModel):
    postback_id: str
    accepted: bool
    duplicate: bool


STANDARD_DISCLAIMERS = [
    "The service does not make credit decisions.",
    "Final decision is made by the bank.",
    "The result is preliminary and based only on the information provided.",
    "Some offers are advertising/referral offers.",
    "We may receive compensation for a referral.",
]
