from src.offers.risk_profile import assess_risk_profile
from src.offers.schemas import CreditProfileInput


def profile():
    return CreditProfileInput.model_validate(
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


class FakeScoringService:
    def __init__(self, coverage):
        self.coverage = coverage

    def score(self, features, request_id=None):
        assert "AMT_CREDIT" in features
        return {
            "default_probability": 0.2,
            "risk_band": "medium",
            "model_version": "test-v1",
            "input_quality": {
                "supplied_feature_coverage": self.coverage,
                "warnings": ["diagnostic"],
            },
        }


def test_bundle_unavailable_is_a_safe_fallback():
    result = assess_risk_profile(profile(), None)
    assert result.risk_score_available is False
    assert result.risk_band == "unknown"
    assert result.warnings == ["Model bundle unavailable"]


def test_low_coverage_score_is_not_exposed_and_diagnostics_propagate():
    result = assess_risk_profile(profile(), FakeScoringService(0.2))
    assert result.risk_score_available is False
    assert result.data_coverage == 0.2
    assert "diagnostic" in result.warnings
    assert any("coverage is low" in warning for warning in result.warnings)


def test_sufficient_coverage_exposes_risk_not_approval_probability():
    result = assess_risk_profile(profile(), FakeScoringService(0.75))
    assert result.risk_score_available is True
    assert result.risk_score == 0.2
    assert result.risk_band == "medium"
    assert result.model_version == "test-v1"
