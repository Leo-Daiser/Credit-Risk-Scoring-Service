"""Consumer-safe local explanations for the public profile model.

The estimator contribution is used only to choose and order factors.  Public
copy is grounded in values that can be calculated from the questionnaire and
never describes a model association as a bank rule or causal effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.public_profile.bundle import PublicProfileModelBundle

ExplanationSource = Literal[
    "financial_rule", "ml_explanation", "offer_rule", "user_reported_context"
]


@dataclass(frozen=True)
class PublicFactor:
    code: str
    label: str
    message: str
    actionable: bool
    direction: str
    source: ExplanationSource = "ml_explanation"


# Demographic and household-correlated features are intentionally absent.
# They may remain available to operator diagnostics in richer models, but do
# not make useful or appropriate consumer advice.
FEATURE_POLICY: dict[str, dict[str, Any]] = {
    "pti": {
        "public_code": "debt_load",
        "label": "Доля кредитных платежей в доходе",
        "actionable": True,
    },
    "annuity_income_ratio": {
        "public_code": "new_payment_share",
        "label": "Доля нового платежа в доходе",
        "actionable": True,
    },
    "credit_income_ratio": {
        "public_code": "amount_to_income",
        "label": "Сумма кредита относительно вашего дохода",
        "actionable": True,
    },
    "existing_monthly_payments": {
        "public_code": "current_payments",
        "label": "Текущие кредитные платежи",
        "actionable": True,
    },
    "employment_years": {
        "public_code": "employment_stability",
        "label": "Подтверждаемый стаж",
        "actionable": False,
    },
}


def explain_public_profile(
    bundle: PublicProfileModelBundle,
    row: dict[str, Any],
    base_probability: float,
    *,
    limit: int = 3,
) -> tuple[list[PublicFactor], list[PublicFactor]]:
    """Rank safe factors using single-feature local perturbations."""
    impacts: list[tuple[float, str]] = []
    numeric_reference = bundle.reference_stats.get("numeric_medians", {})
    for feature in bundle.feature_names:
        if feature not in FEATURE_POLICY:
            continue
        # Without existing payments, PTI and the new-payment share are the same
        # value. Showing both can create contradictory public explanations.
        if (
            feature == "annuity_income_ratio"
            and float(row.get("existing_monthly_payments") or 0.0) == 0
        ):
            continue
        reference = numeric_reference.get(feature)
        if reference is None or row.get(feature) == reference:
            continue
        candidate = dict(row)
        candidate[feature] = reference
        probability = float(
            bundle.model.predict_proba(bundle.prepare_frame([candidate]))[0, 1]
        )
        impacts.append((base_probability - probability, feature))
    impacts.sort(key=lambda item: abs(item[0]), reverse=True)

    strengths: list[PublicFactor] = []
    limitations: list[PublicFactor] = []
    used_codes: set[str] = set()
    for impact, feature in impacts:
        policy = FEATURE_POLICY[feature]
        code = str(policy["public_code"])
        if code in used_codes:
            continue
        used_codes.add(code)
        limiting = impact > 0
        factor = PublicFactor(
            code=code,
            label=str(policy["label"]),
            message=_value_message(feature, row, limiting=limiting),
            actionable=bool(policy["actionable"]),
            direction="limiting" if limiting else "strength",
        )
        (limitations if limiting else strengths).append(factor)
    return strengths[:limit], limitations[:limit]


def _value_message(feature: str, row: dict[str, Any], *, limiting: bool) -> str:
    if feature == "pti":
        percent = max(float(row.get("pti") or 0.0), 0.0) * 100
        direction = (
            "немного ограничивает текущий сценарий"
            if limiting
            else "поддерживает текущий сценарий"
        )
        return (
            f"Текущие и новый кредитные платежи составляют около {percent:.0f}% "
            f"указанного дохода. Такая нагрузка {direction} в оценке Riskline."
        )
    if feature == "annuity_income_ratio":
        percent = max(float(row.get("annuity_income_ratio") or 0.0), 0.0) * 100
        direction = "заметно увеличивает нагрузку" if limiting else "оставляет умеренную нагрузку"
        return (
            f"Ориентировочный новый платёж занимает около {percent:.0f}% "
            f"указанного дохода и {direction}."
        )
    if feature == "credit_income_ratio":
        percent = max(float(row.get("credit_income_ratio") or 0.0), 0.0) * 100
        direction = "ограничивает" if limiting else "поддерживает"
        return (
            f"Запрошенная сумма равна примерно {percent:.0f}% вашего годового "
            f"дохода; это соотношение {direction} текущую оценку Riskline."
        )
    if feature == "existing_monthly_payments":
        value = max(float(row.get("existing_monthly_payments") or 0.0), 0.0)
        if value == 0:
            return "Вы указали, что действующих кредитных платежей нет."
        if limiting:
            return (
                f"Указанные текущие платежи — около {value:,.0f} ₽ в месяц — "
                "увеличивают расчётную долговую нагрузку."
            )
        return (
            f"Указанные текущие платежи — около {value:,.0f} ₽ в месяц — "
            "учтены при расчёте долговой нагрузки."
        )
    years = max(float(row.get("employment_years") or 0.0), 0.0)
    if limiting:
        return (
            f"Указанный подтверждаемый стаж — около {years:g} лет. В модели этот "
            "контекст ограничивает текущую оценку, но не является решением банка."
        )
    return (
        f"Указанный подтверждаемый стаж — около {years:g} лет. Этот контекст "
        "поддерживает текущую оценку Riskline."
    )


def safe_factor_payload(factor: PublicFactor) -> dict[str, Any]:
    return {
        "code": factor.code,
        "label": factor.label,
        "message": factor.message,
        "actionable": factor.actionable,
        "source": factor.source,
    }
