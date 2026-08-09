from __future__ import annotations

from src.db.models import BankOffer
from src.offers.affordability import estimate_amount_from_band, estimate_annuity_payment
from src.offers.schemas import CreditProfileInput, OfferCalculation


def calculate_offer_terms(
    profile: CreditProfileInput,
    offer: BankOffer,
) -> OfferCalculation:
    requested_amount = profile.requested_amount or estimate_amount_from_band(
        profile.requested_amount_band
    )
    selected_amount = min(max(requested_amount, offer.min_amount), offer.max_amount)
    selected_term = min(
        max(profile.term_months, offer.min_term_months),
        offer.max_term_months,
    )
    adjustments: list[str] = []
    if selected_amount != requested_amount:
        if selected_amount < requested_amount:
            adjustments.append(
                f"Для продукта максимальная сумма — {selected_amount:,.0f} ₽. "
                "Расчёт выполнен по этому лимиту."
            )
        else:
            adjustments.append(
                f"Для продукта минимальная сумма — {selected_amount:,.0f} ₽. "
                "Расчёт выполнен по этому лимиту."
            )
    if selected_term != profile.term_months:
        adjustments.append(
            f"Для продукта доступен срок до {offer.max_term_months} месяцев. "
            f"Расчёт выполнен на {selected_term} месяцев."
        )
    rate_min = offer.annual_rate_min
    rate_max = offer.annual_rate_max
    payment_min = payment_max = None
    total_min = total_max = None
    overpayment_min = overpayment_max = None
    assumptions = [
        "Расчёт предварительный: фактические условия определяет партнёр.",
        "Комиссии и страховка учитываются только если явно указаны в карточке.",
    ]
    if rate_min is not None and rate_max is not None:
        payment_min = estimate_annuity_payment(
            selected_amount, rate_min / 100.0, selected_term
        )
        payment_max = estimate_annuity_payment(
            selected_amount, rate_max / 100.0, selected_term
        )
        total_min = round(payment_min * selected_term, 2)
        total_max = round(payment_max * selected_term, 2)
        overpayment_min = round(max(total_min - selected_amount, 0), 2)
        overpayment_max = round(max(total_max - selected_amount, 0), 2)
    else:
        assumptions.append("Ставка не задана: точный платёж для продукта не рассчитан.")
    return OfferCalculation(
        selected_amount=selected_amount,
        selected_term_months=selected_term,
        annual_rate_min=rate_min,
        annual_rate_max=rate_max,
        monthly_payment_min=payment_min,
        monthly_payment_max=payment_max,
        total_repayment_min=total_min,
        total_repayment_max=total_max,
        overpayment_min=overpayment_min,
        overpayment_max=overpayment_max,
        full_cost_range_text=offer.full_cost_range_text,
        adjustments=adjustments,
        assumptions=assumptions,
    )


def profile_compatibility_label(risk_band: str, model_available: bool) -> str:
    if not model_available:
        return "Совместимо по правилам; ML-профиль временно недоступен"
    return {
        "low": "Хорошо соответствует текущему профилю",
        "medium": "Соответствует текущему профилю",
        "high": "Совместимо с дополнительными ограничениями",
        "very_high": "Ограниченно совместимо с текущим профилем",
    }.get(risk_band, "Совместимо по базовым параметрам")
