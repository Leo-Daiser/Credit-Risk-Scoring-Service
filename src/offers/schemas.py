from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.offers.constraints import (
    PUBLIC_AGE_MAX,
    PUBLIC_AGE_MIN,
    PUBLIC_AMOUNT_MAX,
    PUBLIC_EMPLOYMENT_YEARS_MAX,
    PUBLIC_EMPLOYMENT_YEARS_MIN,
    PUBLIC_EXISTING_PAYMENTS_MAX,
    PUBLIC_MONTHLY_INCOME_MAX,
    PUBLIC_TERM_MAX_MONTHS,
    PUBLIC_TERM_MIN_MONTHS,
)


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


class HousingType(StrEnum):
    OWNED = "owned"
    RENT = "rent"
    FAMILY = "family"
    MUNICIPAL = "municipal"
    EMPLOYER = "employer"
    OTHER = "other"
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
    age: int | None = Field(default=None, ge=PUBLIC_AGE_MIN, le=PUBLIC_AGE_MAX)
    region: str | None = Field(default=None, min_length=1, max_length=64)
    income_band: IncomeBand
    monthly_income: float | None = Field(
        default=None, gt=0, le=PUBLIC_MONTHLY_INCOME_MAX
    )
    employment_type: EmploymentType
    employment_years: float | None = Field(
        default=None,
        ge=PUBLIC_EMPLOYMENT_YEARS_MIN,
        le=PUBLIC_EMPLOYMENT_YEARS_MAX,
    )
    family_members: int | None = Field(default=None, ge=1, le=20)
    children: int | None = Field(default=None, ge=0, le=15)
    housing_type: HousingType = HousingType.UNKNOWN
    owns_car: bool | None = None
    owns_realty: bool | None = None
    requested_amount_band: AmountBand
    requested_amount: float | None = Field(default=None, gt=0, le=PUBLIC_AMOUNT_MAX)
    term_months: int = Field(
        ge=PUBLIC_TERM_MIN_MONTHS, le=PUBLIC_TERM_MAX_MONTHS
    )
    existing_monthly_payments_band: PaymentsBand
    existing_monthly_payments: float | None = Field(
        default=None, ge=0, le=PUBLIC_EXISTING_PAYMENTS_MAX
    )
    credit_history_band: CreditHistoryBand
    loan_purpose: LoanPurpose
    consent_to_process: bool
    consent_to_ad_personalization: bool = False

    @model_validator(mode="after")
    def validate_consent(self) -> CreditProfileInput:
        if not self.consent_to_process:
            raise ValueError("consent_to_process must be true for server-side matching")
        age_ranges = {
            AgeBand.AGE_18_21: (18, 21),
            AgeBand.AGE_22_30: (22, 30),
            AgeBand.AGE_31_45: (31, 45),
            AgeBand.AGE_46_60: (46, 60),
            AgeBand.AGE_60_PLUS: (61, 75),
        }
        if self.age is not None:
            lower, upper = age_ranges[self.age_band]
            if not lower <= self.age <= upper:
                raise ValueError("age does not match age_band")
        if (
            self.age is not None
            and self.employment_years is not None
            and self.employment_years > max(self.age - 14, 0)
        ):
            raise ValueError("employment_years is not plausible for the supplied age")
        if (
            self.family_members is not None
            and self.children is not None
            and self.children >= self.family_members
        ):
            raise ValueError("children must be fewer than family_members")
        if self.requested_amount is not None:
            expected_amount_band = (
                AmountBand.LT_100K
                if self.requested_amount < 100_000
                else AmountBand.FROM_100K_TO_300K
                if self.requested_amount <= 300_000
                else AmountBand.FROM_300K_TO_700K
                if self.requested_amount <= 700_000
                else AmountBand.FROM_700K_TO_1_5M
                if self.requested_amount <= 1_500_000
                else AmountBand.GT_1_5M
            )
            if self.requested_amount_band is not expected_amount_band:
                raise ValueError("requested_amount does not match requested_amount_band")
        if self.monthly_income is not None:
            if self.income_band is IncomeBand.UNKNOWN:
                raise ValueError("exact income cannot be supplied with an unknown band")
            expected_income_band = (
                IncomeBand.LT_50K
                if self.monthly_income < 50_000
                else IncomeBand.FROM_50K_TO_100K
                if self.monthly_income <= 100_000
                else IncomeBand.FROM_100K_TO_150K
                if self.monthly_income <= 150_000
                else IncomeBand.FROM_150K_TO_250K
                if self.monthly_income <= 250_000
                else IncomeBand.GT_250K
            )
            if self.income_band is not expected_income_band:
                raise ValueError("monthly_income does not match income_band")
        if self.existing_monthly_payments is not None:
            if self.existing_monthly_payments_band is PaymentsBand.UNKNOWN:
                raise ValueError("exact payments cannot be supplied with an unknown band")
            expected_payment_band = (
                PaymentsBand.ZERO
                if self.existing_monthly_payments == 0
                else PaymentsBand.LT_10K
                if self.existing_monthly_payments < 10_000
                else PaymentsBand.FROM_10K_TO_30K
                if self.existing_monthly_payments <= 30_000
                else PaymentsBand.FROM_30K_TO_60K
                if self.existing_monthly_payments <= 60_000
                else PaymentsBand.GT_60K
            )
            if self.existing_monthly_payments_band is not expected_payment_band:
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


class PublicProfileFactor(BaseModel):
    code: str
    label: str
    message: str
    actionable: bool = False
    source: Literal[
        "financial_rule", "ml_explanation", "offer_rule", "user_reported_context"
    ] = "ml_explanation"


class RisklineProfileResult(BaseModel):
    anonymous_profile_id: str
    profile_id: str | None = None
    model_available: bool = False
    ml_personalized: bool = False
    risk_band: str
    risk_score_available: bool
    risk_score: float | None = Field(default=None, ge=0, le=1, exclude=True)
    risk_model_version: str | None = Field(default=None, exclude=True)
    requested_amount: float | None = Field(default=None, ge=0, exclude=True)
    risk_signal: str = "unknown"
    riskline_index: int | None = Field(default=None, ge=0, le=100)
    profile_band: str = "insufficient_data"
    affordability_band: AffordabilityBand
    estimated_monthly_payment: float | None = Field(default=None, ge=0)
    pti_value: float | None = Field(default=None, ge=0)
    pti_band: PtiBand
    data_coverage: float = Field(ge=0, le=1)
    confidence_level: ConfidenceLevel
    strengths: list[PublicProfileFactor] = Field(default_factory=list)
    limiting_factors: list[PublicProfileFactor] = Field(default_factory=list)
    actionable_factors: list[PublicProfileFactor] = Field(default_factory=list)
    warnings: list[str]
    disclaimers: list[str]
    profile_bands: ProfileBands


CreditProfileResult = RisklineProfileResult


class OfferCalculation(BaseModel):
    selected_amount: float = Field(ge=0)
    selected_term_months: int = Field(ge=1)
    annual_rate_min: float | None = Field(default=None, ge=0)
    annual_rate_max: float | None = Field(default=None, ge=0)
    monthly_payment_min: float | None = Field(default=None, ge=0)
    monthly_payment_max: float | None = Field(default=None, ge=0)
    total_repayment_min: float | None = Field(default=None, ge=0)
    total_repayment_max: float | None = Field(default=None, ge=0)
    overpayment_min: float | None = Field(default=None, ge=0)
    overpayment_max: float | None = Field(default=None, ge=0)
    full_cost_range_text: str | None = None
    adjustments: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ImprovementScenario(BaseModel):
    scenario_id: str
    factor: str
    title: str
    current_state: str
    suggested_state: str
    expected_direction: str
    effects: list[str]
    trade_off: str
    amount: float
    term_months: int
    existing_monthly_payments: float
    estimated_monthly_payment: float
    pti_value: float | None = None
    affordability_band: AffordabilityBand
    riskline_index: int | None = None
    profile_band: str
    eligible_offer_count: int = Field(ge=0)


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
    profile_compatibility: str = "Совместимо по базовым параметрам"
    calculation: OfferCalculation | None = None


PublicEventType = Literal[
    "landing_viewed",
    "assessment_started",
    "assessment_step_completed",
    "assessment_completed",
    "calculator_used",
    "calculator_continue_clicked",
    "profile_started",
    "profile_completed",
    "profile_scored",
    "profile_result_viewed",
    "improvement_viewed",
    "scenario_changed",
    "scenario_started",
    "scenario_applied",
    "offers_viewed",
    "recommended_offer_viewed",
    "no_eligible_offers_viewed",
    "offer_clicked",
    "partner_transition_viewed",
]


class PublicAnalyticsEventRequest(BaseModel):
    """Allowlisted public product event without arbitrary or financial payloads."""

    model_config = ConfigDict(extra="forbid")

    event_type: PublicEventType
    anonymous_session_id: str | None = Field(default=None, min_length=8, max_length=128)
    page: Literal[
        "landing", "assessment", "credit_calculator", "offers", "result", "scenario"
    ]
    profile_band: str | None = Field(default=None, max_length=32)
    pti_band: str | None = Field(default=None, max_length=32)
    scenario_type: Literal["amount", "term", "payments", "refinance"] | None = None
    offer_position: Literal["recommended", "alternative"] | None = None
    assessment_step: Literal[1, 2, 3, 4] | None = None


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
    total_eligible_offers: int = Field(ge=0)
    disclaimers: list[str]
    ad_disclosure_required: bool = True
    no_eligible_offers: bool = False
    user_explanation: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    why_not_reasons: list[str] = Field(default_factory=list)
    improvement_scenarios: list[ImprovementScenario] = Field(default_factory=list)


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
    "Сервис не принимает кредитных решений.",
    "Финальное решение принимает банк.",
    "Результат предварительный и основан только на указанных данных.",
    "Некоторые предложения являются рекламными или партнёрскими.",
    "Сервис может получить вознаграждение за переход.",
]
