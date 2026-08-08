import math

import pytest
from pydantic import ValidationError

from src.offers.affordability import (
    assign_affordability_band,
    assign_pti_band,
    calculate_pti,
    estimate_annuity_payment,
    estimate_income_from_band,
)
from src.offers.schemas import (
    AffordabilityBand,
    AmountBand,
    CreditProfileInput,
    IncomeBand,
    PtiBand,
)


def valid_profile(**overrides):
    payload = {
        "age_band": "31_45",
        "income_band": "100k_150k",
        "employment_type": "employee",
        "requested_amount_band": "100k_300k",
        "term_months": 24,
        "existing_monthly_payments_band": "zero",
        "credit_history_band": "good",
        "loan_purpose": "cash",
        "consent_to_process": True,
    }
    payload.update(overrides)
    return CreditProfileInput.model_validate(payload)


def test_annuity_known_value_and_zero_rate_are_deterministic():
    assert math.isclose(estimate_annuity_payment(1_000_000, 0.12, 24), 47_073.47)
    assert estimate_annuity_payment(120_000, 0, 12) == 10_000


@pytest.mark.parametrize(
    "args",
    [(-1, 0.1, 12), (1, -0.1, 12), (1, 0.1, 0)],
)
def test_annuity_rejects_invalid_values(args):
    with pytest.raises(ValueError):
        estimate_annuity_payment(*args)


def test_pti_bands_and_unknown_income_are_conservative():
    assert calculate_pti(100_000, 0, 20_000) == 0.2
    assert assign_pti_band(0.2) is PtiBand.LOW
    assert assign_pti_band(0.45) is PtiBand.HIGH
    assert assign_pti_band(None) is PtiBand.UNKNOWN
    assert estimate_income_from_band(IncomeBand.UNKNOWN) is None
    assert (
        assign_affordability_band(None, AmountBand.LT_100K, IncomeBand.UNKNOWN)
        is AffordabilityBand.UNKNOWN
    )


def test_profile_requires_consent_and_rejects_exact_negative_values():
    with pytest.raises(ValidationError, match="consent_to_process"):
        valid_profile(consent_to_process=False)
    with pytest.raises(ValidationError):
        valid_profile(existing_monthly_payments=-1)
