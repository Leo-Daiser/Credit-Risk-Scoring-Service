from __future__ import annotations

from dataclasses import dataclass

from src.db.models import BankOffer
from src.offers.affordability import (
    estimate_amount_from_band,
    estimate_existing_payments_from_band,
)
from src.offers.eligibility import evaluate_offer_eligibility
from src.offers.schemas import (
    AmountBand,
    CreditProfileInput,
    CreditProfileResult,
    ImprovementScenario,
    PaymentsBand,
)
from src.public_profile.service import PublicProfileScoringService


@dataclass(frozen=True)
class _Candidate:
    scenario_id: str
    factor: str
    title: str
    amount: float
    term_months: int
    existing_payments: float
    trade_off: str


def build_improvement_scenarios(
    profile: CreditProfileInput,
    baseline: CreditProfileResult,
    offers: list[BankOffer],
    scoring_service: PublicProfileScoringService | None,
) -> list[ImprovementScenario]:
    """Evaluate realistic changes without persisting raw scenario values."""
    amount = profile.requested_amount or estimate_amount_from_band(
        profile.requested_amount_band
    )
    payments = (
        profile.existing_monthly_payments
        if profile.existing_monthly_payments is not None
        else estimate_existing_payments_from_band(
            profile.existing_monthly_payments_band
        )
        or 0.0
    )
    candidates = _candidates(amount, profile.term_months, payments)
    scenarios: list[ImprovementScenario] = []
    for candidate in candidates:
        updated = profile.model_copy(
            update={
                "requested_amount": round(candidate.amount, 2),
                "requested_amount_band": amount_band(candidate.amount),
                "term_months": candidate.term_months,
                "existing_monthly_payments": round(candidate.existing_payments, 2),
                "existing_monthly_payments_band": payments_band(
                    candidate.existing_payments
                ),
            }
        )
        # model_copy deliberately skips validation; rebuild to keep the public
        # contract identical to an ordinary questionnaire request.
        updated = CreditProfileInput.model_validate(updated.model_dump())
        from src.offers.service import build_profile_result

        result = build_profile_result(updated, scoring_service)
        eligible_count = sum(
            evaluate_offer_eligibility(result, offer).eligible for offer in offers
        )
        baseline_eligible = sum(
            evaluate_offer_eligibility(baseline, offer).eligible for offer in offers
        )
        index_delta = (
            (result.riskline_index or 0) - (baseline.riskline_index or 0)
            if result.model_available and baseline.model_available
            else 0
        )
        pti_improvement = (
            (baseline.pti_value or 0) - (result.pti_value or 0)
            if baseline.pti_value is not None and result.pti_value is not None
            else 0
        )
        if index_delta < 2 and pti_improvement < 0.02 and eligible_count <= baseline_eligible:
            continue
        effects = ["Расчётная долговая нагрузка становится ниже"]
        if result.estimated_monthly_payment < baseline.estimated_monthly_payment:
            effects.insert(0, "Ориентировочный ежемесячный платёж становится ниже")
        if index_delta >= 2:
            effects.append("Предварительный профиль Riskline становится устойчивее")
        if eligible_count > baseline_eligible:
            effects.append("Расширяется число совместимых предложений")
        scenarios.append(
            ImprovementScenario(
                scenario_id=candidate.scenario_id,
                factor=candidate.factor,
                title=candidate.title,
                current_state=_current_state(candidate.factor, amount, profile.term_months, payments),
                suggested_state=_suggested_state(candidate),
                expected_direction="Более комфортная расчётная нагрузка",
                effects=effects,
                trade_off=candidate.trade_off,
                amount=candidate.amount,
                term_months=candidate.term_months,
                existing_monthly_payments=candidate.existing_payments,
                estimated_monthly_payment=result.estimated_monthly_payment,
                pti_value=result.pti_value,
                affordability_band=result.affordability_band,
                riskline_index=result.riskline_index,
                profile_band=result.profile_band,
                eligible_offer_count=eligible_count,
            )
        )
    scenarios.sort(
        key=lambda item: (
            -(item.eligible_offer_count - baseline_eligible),
            -(item.riskline_index or 0),
            item.scenario_id,
        )
    )
    return scenarios[:4]


def amount_band(amount: float) -> AmountBand:
    if amount < 100_000:
        return AmountBand.LT_100K
    if amount <= 300_000:
        return AmountBand.FROM_100K_TO_300K
    if amount <= 700_000:
        return AmountBand.FROM_300K_TO_700K
    if amount <= 1_500_000:
        return AmountBand.FROM_700K_TO_1_5M
    return AmountBand.GT_1_5M


def payments_band(payments: float) -> PaymentsBand:
    if payments <= 0:
        return PaymentsBand.ZERO
    if payments < 10_000:
        return PaymentsBand.LT_10K
    if payments <= 30_000:
        return PaymentsBand.FROM_10K_TO_30K
    if payments <= 60_000:
        return PaymentsBand.FROM_30K_TO_60K
    return PaymentsBand.GT_60K


def _candidates(amount: float, term: int, payments: float) -> list[_Candidate]:
    candidates = [
        _Candidate(
            f"amount-{percent}",
            "amount",
            "Уменьшить сумму",
            max(round(amount * (1 - percent / 100) / 10_000) * 10_000, 10_000),
            term,
            payments,
            "Доступная сумма финансирования будет меньше.",
        )
        for percent in (10, 20, 30)
    ]
    for longer_term in (48, 60, 84):
        if longer_term > term:
            candidates.append(
                _Candidate(
                    f"term-{longer_term}",
                    "term",
                    "Увеличить срок",
                    amount,
                    longer_term,
                    payments,
                    "Ежемесячный платёж ниже, но общая переплата обычно выше.",
                )
            )
            break
    if payments > 0:
        candidates.append(
            _Candidate(
                "payments-refinance",
                "refinance",
                "Проверить рефинансирование",
                amount,
                term,
                round(payments * 0.7 / 1_000) * 1_000,
                "Это сценарий для сравнения, а не обещание снизить действующий платёж.",
            )
        )
    return candidates


def _current_state(factor: str, amount: float, term: int, payments: float) -> str:
    if factor == "amount":
        return f"{amount:,.0f} ₽"
    if factor == "term":
        return f"{term} месяцев"
    return f"Текущие платежи около {payments:,.0f} ₽"


def _suggested_state(candidate: _Candidate) -> str:
    if candidate.factor == "amount":
        return f"{candidate.amount:,.0f} ₽"
    if candidate.factor == "term":
        return f"{candidate.term_months} месяцев"
    return f"Сценарий платежей около {candidate.existing_payments:,.0f} ₽"
