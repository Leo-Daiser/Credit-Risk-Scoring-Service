from __future__ import annotations

import math

from src.offers.schemas import AffordabilityBand, AmountBand, IncomeBand, PaymentsBand, PtiBand

INCOME_ESTIMATES = {
    IncomeBand.LT_50K: 35_000.0,
    IncomeBand.FROM_50K_TO_100K: 65_000.0,
    IncomeBand.FROM_100K_TO_150K: 115_000.0,
    IncomeBand.FROM_150K_TO_250K: 175_000.0,
    IncomeBand.GT_250K: 275_000.0,
}
PAYMENT_ESTIMATES = {
    PaymentsBand.ZERO: 0.0,
    PaymentsBand.LT_10K: 7_500.0,
    PaymentsBand.FROM_10K_TO_30K: 20_000.0,
    PaymentsBand.FROM_30K_TO_60K: 45_000.0,
    PaymentsBand.GT_60K: 75_000.0,
}
AMOUNT_ESTIMATES = {
    AmountBand.LT_100K: 75_000.0,
    AmountBand.FROM_100K_TO_300K: 200_000.0,
    AmountBand.FROM_300K_TO_700K: 500_000.0,
    AmountBand.FROM_700K_TO_1_5M: 1_000_000.0,
    AmountBand.GT_1_5M: 1_750_000.0,
}


def estimate_annuity_payment(amount: float, annual_rate: float, term_months: int) -> float:
    if amount <= 0:
        raise ValueError("amount must be positive")
    if annual_rate < 0:
        raise ValueError("annual_rate cannot be negative")
    if term_months <= 0:
        raise ValueError("term_months must be positive")
    monthly_rate = annual_rate / 12.0
    if monthly_rate == 0:
        return round(amount / term_months, 2)
    factor = math.pow(1 + monthly_rate, term_months)
    return round(amount * monthly_rate * factor / (factor - 1), 2)


def estimate_income_from_band(income_band: IncomeBand) -> float | None:
    return INCOME_ESTIMATES.get(income_band)


def estimate_existing_payments_from_band(payments_band: PaymentsBand) -> float | None:
    return PAYMENT_ESTIMATES.get(payments_band)


def estimate_amount_from_band(amount_band: AmountBand) -> float:
    return AMOUNT_ESTIMATES[amount_band]


def calculate_pti(income: float, existing_payments: float, new_payment: float) -> float:
    if income <= 0:
        raise ValueError("income must be positive")
    if existing_payments < 0 or new_payment < 0:
        raise ValueError("payments cannot be negative")
    return round((existing_payments + new_payment) / income, 6)


def assign_pti_band(pti: float | None) -> PtiBand:
    if pti is None:
        return PtiBand.UNKNOWN
    if pti < 0:
        raise ValueError("pti cannot be negative")
    if pti < 0.25:
        return PtiBand.LOW
    if pti < 0.45:
        return PtiBand.MODERATE
    if pti < 0.65:
        return PtiBand.HIGH
    return PtiBand.VERY_HIGH


def assign_affordability_band(
    pti: float | None,
    requested_amount_band: AmountBand,
    income_band: IncomeBand,
) -> AffordabilityBand:
    if pti is None or income_band is IncomeBand.UNKNOWN:
        return AffordabilityBand.UNKNOWN
    pti_band = assign_pti_band(pti)
    if pti_band is PtiBand.LOW:
        return AffordabilityBand.COMFORTABLE
    if pti_band is PtiBand.MODERATE:
        return AffordabilityBand.MANAGEABLE
    if pti_band is PtiBand.HIGH:
        return AffordabilityBand.STRETCHED
    return AffordabilityBand.UNAFFORDABLE
