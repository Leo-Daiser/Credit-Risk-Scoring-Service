from __future__ import annotations

import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import get_optional_public_profile_scoring_service
from src.api.main import app
from src.core.config import settings
from src.db.base import Base
from src.db.session import get_db
from src.offers.calculations import calculate_offer_terms
from src.offers.eligibility import evaluate_offer_eligibility
from src.offers.providers.demo import DemoOfferProvider
from src.offers.repository import OfferRepository
from src.offers.scenarios import build_improvement_scenarios
from src.offers.schemas import CreditProfileInput
from src.offers.service import build_profile_result
from src.public_profile.bundle import PublicProfileModelBundle
from src.public_profile.mapping import (
    PUBLIC_CATEGORICAL_FEATURES,
    PUBLIC_FEATURES,
    PUBLIC_NUMERIC_FEATURES,
    HomeCreditPublicTrainingAdapter,
    public_feature_row,
)
from src.public_profile.service import PublicProfileScoringService
from src.public_profile.training_schema import (
    PublicProfileTrainingRow,
    validate_normalized_training_frame,
)


class DeterministicPublicEstimator:
    """Small test estimator proving inference is not a calculator alias."""

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        ratio = frame["credit_income_ratio"].astype(float).fillna(1.0)
        pti = frame["pti"].astype(float).fillna(0.8)
        employment = frame["employment_type"].map(
            {"employee": -0.4, "self_employed": 0.0, "unemployed": 0.8}
        ).fillna(0.2)
        logit = -2.4 + 1.2 * ratio + 2.1 * pti + employment
        probability = 1 / (1 + np.exp(-logit))
        return np.column_stack([1 - probability, probability])


def public_bundle() -> PublicProfileModelBundle:
    return PublicProfileModelBundle(
        model=DeterministicPublicEstimator(),
        metadata={
            "bundle_format_version": 1,
            "model_name": "Riskline Public Profile Model",
            "model_version": "public-test-v1",
            "training_source": "synthetic estimator for contract tests",
            "training_date": "2026-08-09T00:00:00+00:00",
            "population_limitations": ["test-only"],
            "risk_bands": [
                {"name": "low", "upper_bound": 0.15},
                {"name": "medium", "upper_bound": 0.3},
                {"name": "high", "upper_bound": 0.5},
                {"name": "very_high", "upper_bound": None},
            ],
            "acceptance_status": "accepted",
        },
        feature_schema={
            "feature_names": PUBLIC_FEATURES,
            "numeric_features": PUBLIC_NUMERIC_FEATURES,
            "categorical_features": PUBLIC_CATEGORICAL_FEATURES,
        },
        reference_stats={
            "numeric_medians": {
                name: 0.25 if name.endswith("ratio") or name == "pti" else 1.0
                for name in PUBLIC_NUMERIC_FEATURES
            },
            "categorical_modes": {
                "employment_type": "employee",
                "housing_type": "owned",
                "owns_car": "no",
                "owns_realty": "yes",
            },
            "probability_quantiles": {
                "q05": 0.05,
                "q25": 0.15,
                "q50": 0.3,
                "q75": 0.5,
                "q95": 0.75,
            },
        },
    )


def profile(**overrides) -> CreditProfileInput:
    payload = {
        "age_band": "31_45",
        "age": 36,
        "income_band": "100k_150k",
        "monthly_income": 130_000,
        "employment_type": "employee",
        "employment_years": 7,
        "family_members": 3,
        "children": 1,
        "housing_type": "owned",
        "owns_car": False,
        "owns_realty": True,
        "requested_amount_band": "300k_700k",
        "requested_amount": 500_000,
        "term_months": 36,
        "existing_monthly_payments_band": "lt_10k",
        "existing_monthly_payments": 5_000,
        "credit_history_band": "good",
        "loan_purpose": "cash",
        "consent_to_process": True,
    }
    payload.update(overrides)
    return CreditProfileInput.model_validate(payload)


def test_public_profile_bundle_loads_and_inference_is_model_derived(tmp_path: Path):
    path = tmp_path / "public.joblib"
    joblib.dump(public_bundle(), path)
    service = PublicProfileScoringService.from_path(path)
    stable = service.score(profile())
    constrained = service.score(
        profile(
            income_band="50k_100k",
            monthly_income=55_000,
            employment_type="unemployed",
            employment_years=0,
            requested_amount_band="700k_1_5m",
            requested_amount=1_100_000,
            existing_monthly_payments_band="30k_60k",
            existing_monthly_payments=45_000,
        )
    )
    assert stable.model_available is True
    assert stable.model_version == "public-test-v1"
    assert stable.default_probability != constrained.default_probability
    assert stable.riskline_index > constrained.riskline_index
    assert stable.risk_band != constrained.risk_band


def test_mapper_uses_normalized_contract_and_explanations_hide_feature_ids():
    mapped = public_feature_row(profile())
    assert list(mapped) == PUBLIC_FEATURES
    assert math.isfinite(mapped["pti"])
    assert not any(name.startswith("AMT_") or name.startswith("DAYS_") for name in mapped)
    assessment = PublicProfileScoringService(public_bundle()).score(profile())
    public_payload = str(assessment.strengths + assessment.limiting_factors)
    assert "AMT_CREDIT" not in public_payload
    assert "DAYS_EMPLOYED" not in public_payload
    assert "credit_income_ratio" not in public_payload
    assert all(
        factor["code"] in {
            "loan_size",
            "loan_term",
            "new_payment_share",
            "amount_to_income",
            "payment_comfort",
            "debt_load",
            "current_payments",
            "income_level",
            "employment_stability",
            "household_budget",
            "employment_context",
            "housing_context",
            "age_context",
            "household_context",
            "family_context",
        }
        for factor in assessment.strengths + assessment.limiting_factors
    )
    assert all(item["actionable"] for item in assessment.actionable_factors)
    assert all(item["code"] not in {"age_context", "family_context"} for item in assessment.actionable_factors)


def test_home_credit_adapter_produces_provider_neutral_training_row():
    raw = pd.DataFrame(
        [{
            "SK_ID_CURR": 1,
            "TARGET": 0,
            "DAYS_BIRTH": -36 * 365,
            "DAYS_EMPLOYED": -7 * 365,
            "AMT_INCOME_TOTAL": 1_560_000,
            "AMT_CREDIT": 500_000,
            "AMT_ANNUITY": 20_000,
            "NAME_INCOME_TYPE": "Working",
            "NAME_HOUSING_TYPE": "House / apartment",
            "CNT_FAM_MEMBERS": 3,
            "CNT_CHILDREN": 1,
            "FLAG_OWN_CAR": "N",
            "FLAG_OWN_REALTY": "Y",
        }]
    )
    normalized = HomeCreditPublicTrainingAdapter().transform(raw)
    validate_normalized_training_frame(normalized)
    assert set(PUBLIC_FEATURES + ["profile_row_id", "target"]) == set(normalized.columns)
    assert normalized.loc[0, "employment_type"] == "employee"
    assert normalized.loc[0, "target"] == 0
    assert set(PublicProfileTrainingRow.model_fields) == set(normalized.columns)


def test_counterfactual_changes_profile_and_demo_provider_contract():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        OfferRepository(session).seed_demo()
        provider = DemoOfferProvider(session)
        assert provider.health()["healthy"] is True
        assert len(provider.list_offers()) >= 8
        assert provider.get_offer(provider.list_offers()[0].record.id) is not None
        baseline_profile = profile(
            income_band="50k_100k",
            monthly_income=70_000,
            requested_amount_band="700k_1_5m",
            requested_amount=800_000,
            existing_monthly_payments_band="10k_30k",
            existing_monthly_payments=20_000,
        )
        service = PublicProfileScoringService(public_bundle())
        baseline = build_profile_result(baseline_profile, service)
        scenarios = build_improvement_scenarios(
            baseline_profile,
            baseline,
            [item.record for item in provider.list_offers()],
            service,
        )
        assert scenarios
        assert any(item.pti_value < baseline.pti_value for item in scenarios if item.pti_value is not None)
        assert any(item.riskline_index != baseline.riskline_index for item in scenarios)
        calculation = calculate_offer_terms(
            baseline_profile, provider.list_offers()[0].record
        )
        assert calculation.monthly_payment_min is not None
        assert calculation.monthly_payment_max >= calculation.monthly_payment_min
        assert calculation.full_cost_range_text


def test_model_risk_signal_materially_changes_offer_compatibility():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    service = PublicProfileScoringService(public_bundle())
    with factory() as session:
        OfferRepository(session).seed_demo()
        offer = DemoOfferProvider(session).list_offers()[0].record
        stable = build_profile_result(profile(), service)
        constrained_input = profile(
            income_band="50k_100k",
            monthly_income=55_000,
            employment_type="unemployed",
            employment_years=0,
            requested_amount_band="700k_1_5m",
            requested_amount=1_100_000,
            existing_monthly_payments_band="30k_60k",
            existing_monthly_payments=45_000,
        )
        constrained = build_profile_result(constrained_input, service)
        assert stable.risk_band in offer.risk_band_policy
        assert constrained.risk_band not in offer.risk_band_policy
        assert evaluate_offer_eligibility(stable, offer).matched_rules["risk_band"] is True
        assert evaluate_offer_eligibility(constrained, offer).matched_rules["risk_band"] is False


def test_fallback_is_observable_and_not_presented_as_ml():
    result = build_profile_result(profile(), None)
    assert result.model_available is False
    assert result.ml_personalized is False
    assert result.riskline_index is None
    assert result.risk_score is None
    serialized = result.model_dump(mode="json")
    assert "risk_score" not in serialized
    assert "risk_model_version" not in serialized
    assert "вероятность одобрения" not in str(serialized).lower()


def test_public_matching_api_uses_model_and_hides_internal_probability():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        OfferRepository(session).seed_demo()

    def override_db():
        with factory() as session:
            yield session

    old_rate_limit = settings.rate_limit_enabled
    settings.rate_limit_enabled = False
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_optional_public_profile_scoring_service] = (
        lambda: PublicProfileScoringService(public_bundle())
    )
    try:
        response = TestClient(app).post(
            "/v1/offers/match",
            json={"profile": profile().model_dump(mode="json")},
        )
    finally:
        app.dependency_overrides.clear()
        settings.rate_limit_enabled = old_rate_limit
        engine.dispose()
    assert response.status_code == 200
    body = response.json()
    assert body["profile_result"]["model_available"] is True
    assert body["profile_result"]["ml_personalized"] is True
    assert body["profile_result"]["riskline_index"] is not None
    assert "risk_score" not in body["profile_result"]
    assert "risk_model_version" not in body["profile_result"]
    assert body["improvement_scenarios"]
    assert body["offers"]
    assert body["offers"][0]["calculation"]["monthly_payment_min"] is not None
    assert "commission" not in str(body).lower()
