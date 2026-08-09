"""Map provider-neutral Riskline questionnaire data into public ML features."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from src.core.config import settings
from src.offers.affordability import (
    calculate_pti,
    estimate_amount_from_band,
    estimate_annuity_payment,
    estimate_existing_payments_from_band,
    estimate_income_from_band,
)
from src.offers.schemas import AgeBand, CreditProfileInput

PUBLIC_NUMERIC_FEATURES = [
    "age",
    "monthly_income",
    "employment_years",
    "family_members",
    "children",
    "requested_amount",
    "term_months",
    "calculated_annuity",
    "existing_monthly_payments",
    "credit_income_ratio",
    "annuity_income_ratio",
    "pti",
    "income_per_family_member",
    "employment_age_ratio",
]
PUBLIC_CATEGORICAL_FEATURES = [
    "employment_type",
    "housing_type",
    "owns_car",
    "owns_realty",
]
PUBLIC_FEATURES = PUBLIC_NUMERIC_FEATURES + PUBLIC_CATEGORICAL_FEATURES

AGE_MIDPOINT = {
    AgeBand.AGE_18_21: 20,
    AgeBand.AGE_22_30: 26,
    AgeBand.AGE_31_45: 38,
    AgeBand.AGE_46_60: 53,
    AgeBand.AGE_60_PLUS: 65,
}
EMPLOYMENT_YEARS_PRIOR = {
    "employee": 4.0,
    "self_employed": 3.0,
    "individual_entrepreneur": 5.0,
    "pensioner": 20.0,
    "unofficial": 2.0,
    "unemployed": 0.0,
    "unknown": 1.0,
}


def public_feature_row(profile: CreditProfileInput) -> dict[str, Any]:
    """Build the stable normalized feature row; no provider feature names escape."""
    age = float(profile.age or AGE_MIDPOINT[profile.age_band])
    income = profile.monthly_income or estimate_income_from_band(profile.income_band)
    amount = profile.requested_amount or estimate_amount_from_band(
        profile.requested_amount_band
    )
    existing = (
        profile.existing_monthly_payments
        if profile.existing_monthly_payments is not None
        else estimate_existing_payments_from_band(
            profile.existing_monthly_payments_band
        )
    )
    employment_years = float(
        profile.employment_years
        if profile.employment_years is not None
        else EMPLOYMENT_YEARS_PRIOR[profile.employment_type.value]
    )
    family_members = float(
        profile.family_members
        if profile.family_members is not None
        else max((profile.children or 0) + 1, 2)
    )
    children = float(profile.children or 0)
    annuity = estimate_annuity_payment(
        amount,
        settings.offer_reference_annual_rate,
        profile.term_months,
    )
    income_value = float(income) if income is not None else np.nan
    existing_value = float(existing) if existing is not None else 0.0
    pti = (
        calculate_pti(income_value, existing_value, annuity)
        if math.isfinite(income_value) and income_value > 0
        else np.nan
    )
    annual_income = income_value * 12.0
    return {
        "age": age,
        "monthly_income": income_value,
        "employment_years": employment_years,
        "family_members": family_members,
        "children": children,
        "requested_amount": float(amount),
        "term_months": float(profile.term_months),
        "calculated_annuity": float(annuity),
        "existing_monthly_payments": existing_value,
        "credit_income_ratio": (
            float(amount) / annual_income if annual_income > 0 else np.nan
        ),
        "annuity_income_ratio": (
            float(annuity) / income_value if income_value > 0 else np.nan
        ),
        "pti": pti,
        "income_per_family_member": (
            income_value / family_members if income_value > 0 and family_members > 0 else np.nan
        ),
        "employment_age_ratio": employment_years / age if age > 0 else np.nan,
        "employment_type": profile.employment_type.value,
        "housing_type": profile.housing_type.value,
        "owns_car": _boolean_category(profile.owns_car),
        "owns_realty": _boolean_category(profile.owns_realty),
    }


def _boolean_category(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def estimate_term_months(
    amount: pd.Series,
    annuity: pd.Series,
    *,
    annual_rate: float = 0.24,
) -> pd.Series:
    """Infer a reproducible term proxy from provider amount and annuity fields."""
    principal = pd.to_numeric(amount, errors="coerce").astype(float)
    payment = pd.to_numeric(annuity, errors="coerce").astype(float)
    monthly_rate = annual_rate / 12.0
    ratio = 1.0 - principal * monthly_rate / payment
    valid = (principal > 0) & (payment > principal * monthly_rate) & (ratio > 0)
    values = pd.Series(np.nan, index=principal.index, dtype="float64")
    values.loc[valid] = -np.log(ratio.loc[valid]) / np.log1p(monthly_rate)
    fallback = principal / payment
    values = values.fillna(fallback).clip(lower=3, upper=120).round()
    return values


def home_credit_to_public_training(raw: pd.DataFrame) -> pd.DataFrame:
    """Adapt legitimate application fields into the provider-neutral training schema."""
    required = {
        "SK_ID_CURR",
        "TARGET",
        "DAYS_BIRTH",
        "DAYS_EMPLOYED",
        "AMT_INCOME_TOTAL",
        "AMT_CREDIT",
        "AMT_ANNUITY",
        "NAME_INCOME_TYPE",
        "NAME_HOUSING_TYPE",
        "CNT_FAM_MEMBERS",
        "CNT_CHILDREN",
        "FLAG_OWN_CAR",
        "FLAG_OWN_REALTY",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"Home Credit public adapter is missing columns: {missing}")
    monthly_income = pd.to_numeric(raw["AMT_INCOME_TOTAL"], errors="coerce") / 12.0
    age = (-pd.to_numeric(raw["DAYS_BIRTH"], errors="coerce") / 365.25).clip(18, 100)
    employment_days = pd.to_numeric(raw["DAYS_EMPLOYED"], errors="coerce")
    employment_years = (-employment_days / 365.25).where(employment_days < 0, 0).clip(0, 65)
    amount = pd.to_numeric(raw["AMT_CREDIT"], errors="coerce")
    annuity = pd.to_numeric(raw["AMT_ANNUITY"], errors="coerce")
    family = pd.to_numeric(raw["CNT_FAM_MEMBERS"], errors="coerce").clip(1, 20)
    children = pd.to_numeric(raw["CNT_CHILDREN"], errors="coerce").clip(0, 15)
    term = estimate_term_months(amount, annuity)
    existing = pd.Series(0.0, index=raw.index)
    pti = (annuity + existing) / monthly_income
    result = pd.DataFrame(
        {
            "profile_row_id": raw["SK_ID_CURR"].astype("int64"),
            "age": age,
            "monthly_income": monthly_income,
            "employment_years": employment_years,
            "family_members": family,
            "children": children,
            "requested_amount": amount,
            "term_months": term,
            "calculated_annuity": annuity,
            "existing_monthly_payments": existing,
            "credit_income_ratio": amount / (monthly_income * 12.0),
            "annuity_income_ratio": annuity / monthly_income,
            "pti": pti,
            "income_per_family_member": monthly_income / family,
            "employment_age_ratio": employment_years / age,
            "employment_type": raw["NAME_INCOME_TYPE"].map(_income_type_mapping()).fillna("unknown"),
            "housing_type": raw["NAME_HOUSING_TYPE"].map(_housing_mapping()).fillna("other"),
            "owns_car": raw["FLAG_OWN_CAR"].map({"Y": "yes", "N": "no"}).fillna("unknown"),
            "owns_realty": raw["FLAG_OWN_REALTY"].map({"Y": "yes", "N": "no"}).fillna("unknown"),
            "target": pd.to_numeric(raw["TARGET"], errors="raise").astype("int64"),
        }
    )
    return result.replace([np.inf, -np.inf], np.nan)


class HomeCreditPublicTrainingAdapter:
    """Replaceable source adapter; public training never consumes raw names directly."""

    source_id = "home_credit_application_train_v1"

    def transform(self, raw: pd.DataFrame) -> pd.DataFrame:
        return home_credit_to_public_training(raw)


def _income_type_mapping() -> dict[str, str]:
    return {
        "Working": "employee",
        "Commercial associate": "self_employed",
        "Businessman": "individual_entrepreneur",
        "Pensioner": "pensioner",
        "State servant": "employee",
        "Student": "unemployed",
        "Unemployed": "unemployed",
        "Maternity leave": "unemployed",
    }


def _housing_mapping() -> dict[str, str]:
    return {
        "House / apartment": "owned",
        "Rented apartment": "rent",
        "With parents": "family",
        "Municipal apartment": "municipal",
        "Office apartment": "employer",
        "Co-op apartment": "other",
    }
