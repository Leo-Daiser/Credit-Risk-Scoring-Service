from __future__ import annotations

from src.db.models import BankOffer
from src.offers.affordability import estimate_amount_from_band
from src.offers.schemas import CreditProfileResult, OfferEligibilityResult

INCOME_ORDER = {
    "unknown": -1,
    "lt_50k": 0,
    "50k_100k": 1,
    "100k_150k": 2,
    "150k_250k": 3,
    "gt_250k": 4,
}
PTI_ORDER = {"low": 0, "moderate": 1, "high": 2, "very_high": 3, "unknown": 4}


def evaluate_offer_eligibility(
    profile: CreditProfileResult,
    offer: BankOffer,
) -> OfferEligibilityResult:
    blocking: list[str] = []
    warnings: list[str] = []
    matched: dict[str, object] = {}
    bands = profile.profile_bands
    amount = profile.requested_amount or estimate_amount_from_band(
        bands.requested_amount_band
    )

    if not offer.is_active:
        blocking.append("offer_inactive")
    matched["amount"] = offer.min_amount <= amount <= offer.max_amount
    if not matched["amount"]:
        blocking.append("amount_out_of_range")
    matched["term"] = offer.min_term_months <= bands.term_months <= offer.max_term_months
    if not matched["term"]:
        blocking.append("term_out_of_range")
    matched["age_band"] = bands.age_band.value in offer.allowed_age_bands
    if not matched["age_band"]:
        blocking.append("age_band_not_allowed")
    matched["employment_type"] = bands.employment_type.value in offer.allowed_employment_types
    if not matched["employment_type"]:
        blocking.append("employment_type_not_allowed")
    matched["credit_history"] = (
        bands.credit_history_band.value in offer.allowed_credit_history_bands
    )
    if not matched["credit_history"]:
        blocking.append("credit_history_not_allowed")
    if bands.income_band.value == "unknown":
        warnings.append("income_unknown")
        matched["income"] = False
    else:
        matched["income"] = (
            INCOME_ORDER[bands.income_band.value] >= INCOME_ORDER[offer.min_income_band]
        )
        if not matched["income"]:
            blocking.append("income_below_minimum")
    if profile.pti_band.value == "unknown":
        warnings.append("pti_unknown")
        matched["pti"] = False
    else:
        matched["pti"] = PTI_ORDER[profile.pti_band.value] <= PTI_ORDER[offer.max_pti_band]
        if not matched["pti"]:
            blocking.append("pti_above_maximum")
    matched["risk_band"] = profile.risk_band in offer.risk_band_policy
    if not matched["risk_band"]:
        blocking.append("risk_band_not_allowed")
    if offer.product_type == "refinance":
        has_existing_debt = (
            bands.existing_monthly_payments_band.value not in {"zero", "unknown"}
        )
        matched["refinance_context"] = has_existing_debt
        if not has_existing_debt:
            blocking.append("refinance_requires_existing_debt")
    if offer.product_type == "car":
        purpose_matches = bands.loan_purpose.value == "car"
        matched["car_purpose"] = purpose_matches
        if not purpose_matches:
            blocking.append("product_purpose_not_compatible")
    if offer.allowed_regions and bands.region is None:
        warnings.append("region_unknown")
        matched["region"] = False
    else:
        matched["region"] = not offer.allowed_regions or bands.region in offer.allowed_regions
        if not matched["region"]:
            blocking.append("region_not_allowed")
    reasons = [key for key, value in matched.items() if value is True]
    return OfferEligibilityResult(
        offer_id=offer.id,
        eligible=not blocking,
        reasons=reasons,
        blocking_reasons=blocking,
        soft_warnings=warnings,
        matched_rules=matched,
    )
