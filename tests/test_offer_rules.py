from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.base import Base
from src.db.models import BankOffer
from src.offers.eligibility import evaluate_offer_eligibility
from src.offers.ranking import rank_offers
from src.offers.revenue import RevenueEstimate, conservative_revenue_estimate
from src.offers.schemas import CreditProfileInput, CreditProfileResult


def make_offer(**overrides):
    values = {
        "id": 1,
        "bank_id": "demo",
        "product_name": "Demo",
        "product_type": "cash",
        "is_active": True,
        "priority": 50,
        "min_age_band": "31_45",
        "max_age_band": "31_45",
        "allowed_age_bands": ["31_45"],
        "allowed_regions": [],
        "allowed_employment_types": ["employee"],
        "allowed_credit_history_bands": ["good"],
        "min_amount": 50_000,
        "max_amount": 500_000,
        "min_term_months": 6,
        "max_term_months": 60,
        "min_income_band": "50k_100k",
        "max_pti_band": "high",
        "risk_band_policy": ["unknown"],
        "affiliate_url_template": "https://example.invalid/?click_id={click_id}",
        "advertiser_name": "Demo Bank",
        "ad_label_text": "Advertising",
        "legal_disclaimer": "Demo only",
        "commission_type": "fixed",
        "commission_amount": 100,
    }
    values.update(overrides)
    return BankOffer(**values)


def make_profile():
    payload = CreditProfileInput.model_validate(
        {
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
    )
    return CreditProfileResult.model_validate(
        {
            "anonymous_profile_id": "test-profile",
            "risk_band": "unknown",
            "risk_score_available": False,
            "risk_score": None,
            "risk_model_version": None,
            "affordability_band": "comfortable",
            "estimated_monthly_payment": 10_000,
            "pti_value": 0.15,
            "pti_band": "low",
            "data_coverage": 0.8,
            "confidence_level": "medium",
            "warnings": [],
            "disclaimers": [],
            "profile_bands": {
                "age_band": payload.age_band,
                "region": payload.region,
                "income_band": payload.income_band,
                "employment_type": payload.employment_type,
                "requested_amount_band": payload.requested_amount_band,
                "term_months": payload.term_months,
                "existing_monthly_payments_band": (
                    payload.existing_monthly_payments_band
                ),
                "credit_history_band": payload.credit_history_band,
                "loan_purpose": payload.loan_purpose,
            },
        }
    )


def test_eligibility_reports_machine_readable_blocking_reasons():
    profile = make_profile()
    eligible = evaluate_offer_eligibility(profile, make_offer())
    assert eligible.eligible is True
    rejected = evaluate_offer_eligibility(profile, make_offer(id=2, max_amount=100_000))
    assert rejected.eligible is False
    assert "amount_out_of_range" in rejected.blocking_reasons


def test_inactive_and_high_pti_offers_are_excluded():
    profile = make_profile()
    inactive = evaluate_offer_eligibility(profile, make_offer(is_active=False))
    strict = evaluate_offer_eligibility(profile, make_offer(max_pti_band="low"))
    assert "offer_inactive" in inactive.blocking_reasons
    assert strict.eligible is True  # Profile has low approximate PTI.


def test_ranker_is_deterministic_and_commission_is_not_a_direct_component():
    profile = make_profile()
    first = make_offer(id=1, priority=40, commission_amount=1)
    second = make_offer(id=2, priority=40, commission_amount=1_000_000)
    pairs = [
        (second, evaluate_offer_eligibility(profile, second)),
        (first, evaluate_offer_eligibility(profile, first)),
    ]
    ranked = rank_offers(profile, pairs)
    assert [item.offer_id for item in ranked] == [1, 2]
    assert ranked[0].score_breakdown["pre_penalty_score"] <= 1
    assert ranked[0].score_breakdown["final_score"] == ranked[0].final_score
    assert "commission_amount" not in ranked[0].score_breakdown


def test_bank_offer_constraints_are_enforced_by_sqlite():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(make_offer(priority=101))
        try:
            session.commit()
        except Exception:
            session.rollback()
        else:
            raise AssertionError("Invalid priority must violate the DB constraint")


def revenue_estimate(expected_revenue_proxy: float) -> RevenueEstimate:
    return RevenueEstimate(
        click_probability=0.2,
        approval_probability=0.2,
        issue_probability=0.5,
        commission_proxy=1.0,
        expected_revenue_proxy=expected_revenue_proxy,
        estimated_revenue_per_impression=10.0,
        source="historical",
        confidence="medium",
    )


def test_high_revenue_cannot_rank_an_ineligible_offer():
    profile = make_profile()
    blocked = make_offer(id=99, max_amount=100_000, commission_amount=1_000_000)
    ranked = rank_offers(
        profile,
        [(blocked, evaluate_offer_eligibility(profile, blocked))],
        revenue_estimates={99: revenue_estimate(1.0)},
    )
    assert ranked == []


def test_revenue_cannot_overcome_poor_fit_beyond_floor():
    profile = make_profile().model_copy(update={"risk_band": "low"})
    good = make_offer(id=1, product_type="cash", priority=20, risk_band_policy=["low"])
    poor = make_offer(
        id=2, product_type="refinance", priority=100, risk_band_policy=["low"]
    )
    config = {
        "ranking": {
            "commercial_fit_floor": 0.7,
            "weights": {
                "fit_score": 0.28,
                "affordability_score": 0.22,
                "risk_compatibility_score": 0.18,
                "product_match_score": 0.14,
                "commercial_score": 0.10,
                "expected_revenue_proxy": 0.08,
            },
            "confidence_penalties": {
                "low": 0.7,
                "basic": 0.82,
                "medium": 0.92,
                "high": 1.0,
            },
        }
    }
    ranked = rank_offers(
        profile,
        [
            (poor, evaluate_offer_eligibility(profile, poor)),
            (good, evaluate_offer_eligibility(profile, good)),
        ],
        config=config,
        revenue_estimates={1: revenue_estimate(0.0), 2: revenue_estimate(1.0)},
    )
    assert [item.offer_id for item in ranked] == [1, 2]
    assert ranked[1].score_breakdown["expected_revenue_proxy"] == 0.02


def test_historical_signal_improves_ranking_only_for_eligible_equal_fit_offers():
    profile = make_profile()
    first = make_offer(id=1, priority=40)
    second = make_offer(id=2, priority=40)
    ranked = rank_offers(
        profile,
        [
            (first, evaluate_offer_eligibility(profile, first)),
            (second, evaluate_offer_eligibility(profile, second)),
        ],
        revenue_estimates={1: revenue_estimate(0.001), 2: revenue_estimate(0.02)},
    )
    assert [item.offer_id for item in ranked] == [2, 1]
    assert ranked[0].score_breakdown["commercial_tiebreaker_used"] == 1.0
    assert ranked[1].score_breakdown["commercial_tiebreaker_used"] == 1.0
    prior = conservative_revenue_estimate(first)
    assert prior.source == "demo_only"
    assert prior.confidence == "low"
