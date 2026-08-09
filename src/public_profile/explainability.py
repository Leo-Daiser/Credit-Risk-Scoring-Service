"""Human-readable, privacy-safe local explanations for the public profile model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.public_profile.bundle import PublicProfileModelBundle


@dataclass(frozen=True)
class PublicFactor:
    code: str
    label: str
    message: str
    actionable: bool
    direction: str


FEATURE_POLICY: dict[str, dict[str, Any]] = {
    "requested_amount": {
        "public_code": "loan_size",
        "label": "Сумма кредита относительно бюджета",
        "actionable": True,
        "positive": "Запрошенная сумма соразмерна указанному бюджету.",
        "negative": "Запрошенная сумма высока относительно указанного бюджета.",
    },
    "term_months": {
        "public_code": "loan_term",
        "label": "Выбранный срок",
        "actionable": True,
        "positive": "Выбранный срок поддерживает умеренный платёж.",
        "negative": "Выбранный срок создаёт повышенный ежемесячный платёж.",
    },
    "calculated_annuity": {
        "public_code": "new_payment_share",
        "label": "Доля нового платежа в доходе",
        "actionable": True,
        "positive": "Ориентировочный новый платёж умерен относительно дохода.",
        "negative": "Ориентировочный новый платёж занимает заметную долю дохода.",
    },
    "credit_income_ratio": {
        "public_code": "amount_to_income",
        "label": "Сумма кредита относительно дохода",
        "actionable": True,
        "positive": "Соотношение суммы и дохода выглядит устойчиво.",
        "negative": "Сумма кредита велика относительно годового дохода.",
    },
    "annuity_income_ratio": {
        "public_code": "payment_comfort",
        "label": "Комфорт нового платежа",
        "actionable": True,
        "positive": "Новый платёж укладывается в умеренную долю дохода.",
        "negative": "Новый платёж повышает нагрузку на ежемесячный бюджет.",
    },
    "pti": {
        "public_code": "debt_load",
        "label": "Совокупная долговая нагрузка",
        "actionable": True,
        "positive": "Совокупная долговая нагрузка остаётся умеренной.",
        "negative": "Совокупная долговая нагрузка ограничивает устойчивость профиля.",
    },
    "existing_monthly_payments": {
        "public_code": "current_payments",
        "label": "Текущие кредитные платежи",
        "actionable": True,
        "positive": "Текущие платежи оставляют запас для нового обязательства.",
        "negative": "Текущие платежи заметно уменьшают свободный бюджет.",
    },
    "monthly_income": {
        "public_code": "income_level",
        "label": "Уровень дохода",
        "actionable": False,
        "positive": "Указанный доход поддерживает финансовую устойчивость профиля.",
        "negative": "Доход ограничивает комфорт выбранной суммы и срока.",
    },
    "employment_years": {
        "public_code": "employment_stability",
        "label": "Стаж",
        "actionable": False,
        "positive": "Продолжительный стаж поддерживает устойчивость профиля.",
        "negative": "Короткий стаж снижает уверенность предварительной оценки.",
    },
    "income_per_family_member": {
        "public_code": "household_budget",
        "label": "Доход на члена семьи",
        "actionable": False,
        "positive": "Доход на члена семьи поддерживает запас бюджета.",
        "negative": "Доход на члена семьи ограничивает запас бюджета.",
    },
    "employment_type": {
        "public_code": "employment_context",
        "label": "Тип занятости",
        "actionable": False,
        "positive": "Указанный тип занятости поддерживает полноту профиля.",
        "negative": "Для указанного типа занятости оценка более ограничена.",
    },
    "housing_type": {
        "public_code": "housing_context",
        "label": "Жилищная ситуация",
        "actionable": False,
        "positive": "Жилищная ситуация поддерживает устойчивость профиля.",
        "negative": "Жилищная ситуация увеличивает неопределённость оценки.",
    },
    "age": {
        "public_code": "age_context",
        "label": "Возрастная группа",
        "actionable": False,
        "positive": "Возрастная группа соответствует обучающей выборке модели.",
        "negative": "Для возрастной группы оценка имеет дополнительные ограничения.",
    },
    "family_members": {
        "public_code": "household_context",
        "label": "Размер семьи",
        "actionable": False,
        "positive": "Указанный состав семьи не ограничивает оценку.",
        "negative": "Состав семьи влияет на доступный бюджет.",
    },
    "children": {
        "public_code": "family_context",
        "label": "Состав семьи",
        "actionable": False,
        "positive": "Состав семьи учтён в предварительном профиле.",
        "negative": "Состав семьи влияет на доступный бюджет.",
    },
}


def explain_public_profile(
    bundle: PublicProfileModelBundle,
    row: dict[str, Any],
    base_probability: float,
    *,
    limit: int = 4,
) -> tuple[list[PublicFactor], list[PublicFactor]]:
    """Use local single-feature perturbations; numeric impacts never leave the API."""
    impacts: list[tuple[float, str]] = []
    numeric_reference = bundle.reference_stats.get("numeric_medians", {})
    categorical_reference = bundle.reference_stats.get("categorical_modes", {})
    for feature in bundle.feature_names:
        if feature not in FEATURE_POLICY:
            continue
        reference = (
            numeric_reference.get(feature)
            if feature in bundle.feature_schema["numeric_features"]
            else categorical_reference.get(feature)
        )
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
    for impact, feature in impacts:
        policy = FEATURE_POLICY[feature]
        direction = "limiting" if impact > 0 else "strength"
        factor = PublicFactor(
            code=str(policy["public_code"]),
            label=str(policy["label"]),
            message=str(policy["negative"] if impact > 0 else policy["positive"]),
            actionable=bool(policy["actionable"]),
            direction=direction,
        )
        (limitations if impact > 0 else strengths).append(factor)
    return strengths[:limit], limitations[:limit]


def safe_factor_payload(factor: PublicFactor) -> dict[str, Any]:
    return {
        "code": factor.code,
        "label": factor.label,
        "message": factor.message,
        "actionable": factor.actionable,
    }
