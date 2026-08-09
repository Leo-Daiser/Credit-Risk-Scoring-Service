from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import (
    AnonymousSession,
    BankOffer,
    CreditProfileEvent,
    OfferClick,
    OfferImpression,
    PartnerPostback,
)
from src.offers.affordability import (
    assign_affordability_band,
    assign_pti_band,
    calculate_pti,
    estimate_amount_from_band,
    estimate_annuity_payment,
    estimate_existing_payments_from_band,
    estimate_income_from_band,
)
from src.offers.analytics import record_funnel_event
from src.offers.eligibility import evaluate_offer_eligibility
from src.offers.experiments import assign_experiment_variant
from src.offers.partners.base import PartnerPostbackEnvelope
from src.offers.partners.registry import get_partner_adapter
from src.offers.partners.signatures import canonical_payload_bytes
from src.offers.ranking import rank_offers
from src.offers.repository import OfferRepository
from src.offers.revenue import build_revenue_estimates
from src.offers.risk_profile import ScoringProtocol, assess_risk_profile
from src.offers.schemas import (
    STANDARD_DISCLAIMERS,
    ClickRequest,
    ClickResponse,
    ConfidenceLevel,
    CreditProfileInput,
    CreditProfileResult,
    MatchContext,
    OfferMatchResponse,
    PartnerPostbackRequest,
    PartnerPostbackResponse,
    ProfileBands,
    RankedOfferPublic,
)


class CommercialNotFoundError(LookupError):
    pass


class CommercialConflictError(RuntimeError):
    pass


def _confidence(profile: CreditProfileInput, risk_coverage: float) -> tuple[float, ConfidenceLevel]:
    known = [
        profile.income_band.value != "unknown",
        profile.employment_type.value != "unknown",
        profile.existing_monthly_payments_band.value != "unknown",
        profile.credit_history_band.value != "unknown",
        profile.region is not None,
    ]
    public_coverage = sum(known) / len(known)
    combined = round(0.8 * public_coverage + 0.2 * risk_coverage, 4)
    if combined >= 0.9:
        return combined, ConfidenceLevel.HIGH
    if combined >= 0.7:
        return combined, ConfidenceLevel.MEDIUM
    if combined >= 0.45:
        return combined, ConfidenceLevel.BASIC
    return combined, ConfidenceLevel.LOW


def build_profile_result(
    profile: CreditProfileInput,
    scoring_service: ScoringProtocol | None = None,
    *,
    profile_id: str | None = None,
) -> CreditProfileResult:
    amount = profile.requested_amount or estimate_amount_from_band(profile.requested_amount_band)
    income = estimate_income_from_band(profile.income_band)
    existing_payments = (
        profile.existing_monthly_payments
        if profile.existing_monthly_payments is not None
        else estimate_existing_payments_from_band(profile.existing_monthly_payments_band)
    )
    payment = estimate_annuity_payment(
        amount,
        settings.offer_reference_annual_rate,
        profile.term_months,
    )
    pti = (
        calculate_pti(income, existing_payments, payment)
        if income is not None and existing_payments is not None
        else None
    )
    pti_band = assign_pti_band(pti)
    risk = assess_risk_profile(profile, scoring_service)
    coverage, confidence = _confidence(profile, risk.data_coverage)
    warnings = list(risk.warnings)
    warnings.append("No credit bureau data or bank underwriting data is used")
    if pti_band.value in {"high", "very_high"}:
        warnings.append("Approximate debt burden is high")
    if pti is None:
        warnings.append("PTI is unavailable because income or existing payments are unknown")
    return CreditProfileResult(
        anonymous_profile_id=profile_id or str(uuid4()),
        risk_band=risk.risk_band,
        risk_score_available=risk.risk_score_available,
        risk_score=risk.risk_score,
        risk_model_version=risk.model_version,
        affordability_band=assign_affordability_band(
            pti, profile.requested_amount_band, profile.income_band
        ),
        estimated_monthly_payment=payment,
        pti_value=pti,
        pti_band=pti_band,
        data_coverage=coverage,
        confidence_level=confidence,
        warnings=warnings,
        disclaimers=STANDARD_DISCLAIMERS,
        profile_bands=ProfileBands(
            age_band=profile.age_band,
            region=profile.region,
            income_band=profile.income_band,
            employment_type=profile.employment_type,
            requested_amount_band=profile.requested_amount_band,
            term_months=profile.term_months,
            existing_monthly_payments_band=profile.existing_monthly_payments_band,
            credit_history_band=profile.credit_history_band,
            loan_purpose=profile.loan_purpose,
        ),
    )


def ensure_anonymous_session(
    session: Session, context: MatchContext | None
) -> AnonymousSession | None:
    if context is None or context.anonymous_session_id is None:
        return None
    key_hash = hashlib.sha256(context.anonymous_session_id.encode()).hexdigest()
    anonymous = session.scalar(
        select(AnonymousSession).where(AnonymousSession.session_key_hash == key_hash)
    )
    if anonymous is None:
        anonymous = AnonymousSession(
            session_key_hash=key_hash,
            source=context.source,
            utm_source=context.utm_source,
            utm_medium=context.utm_medium,
            utm_campaign=context.utm_campaign,
        )
        session.add(anonymous)
        session.flush()
    else:
        anonymous.last_seen_at = datetime.now()
    return anonymous


def persist_profile_event(
    session: Session,
    result: CreditProfileResult,
    context: MatchContext | None = None,
) -> CreditProfileEvent:
    anonymous = ensure_anonymous_session(session, context)
    bands = result.profile_bands
    event = CreditProfileEvent(
        anonymous_session_id=anonymous.id if anonymous else None,
        profile_id=result.anonymous_profile_id,
        risk_band=result.risk_band,
        pti_band=result.pti_band.value,
        affordability_band=result.affordability_band.value,
        age_band=bands.age_band.value,
        region=bands.region,
        income_band=bands.income_band.value,
        requested_amount_band=bands.requested_amount_band.value,
        term_months=bands.term_months,
        employment_type=bands.employment_type.value,
        credit_history_band=bands.credit_history_band.value,
        loan_purpose=bands.loan_purpose.value,
        data_coverage=result.data_coverage,
        model_version=result.risk_model_version,
    )
    session.add(event)
    session.flush()
    return event


def match_offers(
    session: Session,
    profile: CreditProfileInput,
    limit: int,
    context: MatchContext | None,
    scoring_service: ScoringProtocol | None = None,
) -> OfferMatchResponse:
    result = build_profile_result(profile, scoring_service)
    profile_event = persist_profile_event(session, result, context)
    experiment_variant = assign_experiment_variant(
        context.anonymous_session_id if context else None
    )
    for event_type in (
        "profile_started",
        "profile_completed",
        "profile_submitted",
        "profile_scored",
        "offers_requested",
    ):
        record_funnel_event(
            session,
            event_type,
            anonymous_session_id=profile_event.anonymous_session_id,
            profile_id=result.anonymous_profile_id,
            risk_band=result.risk_band,
            pti_band=result.pti_band.value,
            experiment_variant=experiment_variant,
        )
    repository = OfferRepository(session)
    active_offers = repository.list_active()
    evaluated = [
        (offer, evaluate_offer_eligibility(result, offer)) for offer in active_offers
    ]
    revenue_estimates = build_revenue_estimates(session, active_offers)
    ranked = rank_offers(
        result,
        evaluated,
        context.model_dump() if context else None,
        revenue_estimates=revenue_estimates,
        experiment_variant=experiment_variant,
    )[:limit]
    for item in ranked:
        session.add(
            OfferImpression(
                anonymous_session_id=profile_event.anonymous_session_id,
                profile_id=result.anonymous_profile_id,
                offer_id=item.offer_id,
                rank=item.rank,
                score=item.final_score,
                score_breakdown_json=item.score_breakdown,
                experiment_variant=experiment_variant,
            )
        )
    record_funnel_event(
        session,
        "offers_shown" if ranked else "no_eligible_offers",
        anonymous_session_id=profile_event.anonymous_session_id,
        profile_id=result.anonymous_profile_id,
        risk_band=result.risk_band,
        pti_band=result.pti_band.value,
        experiment_variant=experiment_variant,
        event_value=str(len(ranked)),
    )
    record_funnel_event(
        session,
        "result_viewed",
        anonymous_session_id=profile_event.anonymous_session_id,
        profile_id=result.anonymous_profile_id,
        risk_band=result.risk_band,
        pti_band=result.pti_band.value,
        experiment_variant=experiment_variant,
    )
    for item in ranked:
        record_funnel_event(
            session,
            "offer_card_viewed",
            anonymous_session_id=profile_event.anonymous_session_id,
            profile_id=result.anonymous_profile_id,
            offer_id=item.offer_id,
            risk_band=result.risk_band,
            pti_band=result.pti_band.value,
            experiment_variant=experiment_variant,
        )
    if not ranked:
        record_funnel_event(
            session,
            "no_eligible_offers_viewed",
            anonymous_session_id=profile_event.anonymous_session_id,
            profile_id=result.anonymous_profile_id,
            risk_band=result.risk_band,
            pti_band=result.pti_band.value,
            experiment_variant=experiment_variant,
        )
    session.commit()
    offer_map = {offer.id: offer for offer in active_offers}
    public_offers = [
        RankedOfferPublic(
            offer_id=item.offer_id,
            rank=item.rank,
            bank_id=item.bank_id,
            product_name=item.product_name,
            product_type=offer_map[item.offer_id].product_type,
            advertiser_name=item.advertiser_name,
            is_demo=offer_map[item.offer_id].partner_id == "demo",
            min_amount=offer_map[item.offer_id].min_amount,
            max_amount=offer_map[item.offer_id].max_amount,
            min_term_months=offer_map[item.offer_id].min_term_months,
            max_term_months=offer_map[item.offer_id].max_term_months,
            positive_reasons=_public_match_reasons(
                item.match_reasons,
                purpose_match=(
                    result.profile_bands.loan_purpose.value
                    == offer_map[item.offer_id].product_type
                ),
            ),
            warnings=list(
                dict.fromkeys(
                    _public_warnings(item.warnings, result)
                    + offer_map[item.offer_id].display_warnings
                )
            ),
            disclosure=(
                f"{item.ad_disclosure} "
                f"{_compensation_disclosure(offer_map[item.offer_id])} "
                f"{offer_map[item.offer_id].legal_disclaimer}"
            ),
            ad_disclosure=(
                f"{item.ad_disclosure} "
                f"{_compensation_disclosure(offer_map[item.offer_id])}"
            ),
            confidence_level=result.confidence_level,
            main_benefit=offer_map[item.offer_id].main_benefit,
            full_cost_range_text=offer_map[item.offer_id].full_cost_range_text,
            compensation_disclosure=_compensation_disclosure(offer_map[item.offer_id]),
            legal_disclaimer=offer_map[item.offer_id].legal_disclaimer,
            cta_text=offer_map[item.offer_id].cta_text,
            redirect_url=item.redirect_url,
        )
        for item in ranked
    ]
    return OfferMatchResponse(
        profile_result=result,
        offers=public_offers,
        disclaimers=STANDARD_DISCLAIMERS,
        no_eligible_offers=not public_offers,
        user_explanation=(
            None
            if public_offers
            else "По указанным диапазонам подходящих предложений пока нет. "
            "Попробуйте скорректировать параметры или вернуться к подбору позже."
        ),
        suggestions=(
            []
            if public_offers
            else [
                "Попробуйте уменьшить диапазон суммы.",
                "Рассмотрите более длинный срок.",
                "Снизьте текущую долговую нагрузку, если это возможно.",
                "Выберите рефинансирование, если цель — объединить текущие платежи.",
                "Уточните поля, отмеченные как неизвестные.",
            ]
        ),
        why_not_reasons=(
            []
            if public_offers
            else [
                "Доступные предложения не прошли консервативную проверку диапазонов.",
                "Мы не показываем заведомо несовместимые рекламные предложения.",
            ]
        ),
    )


def _compensation_disclosure(offer: BankOffer) -> str:
    return (
        offer.compensation_disclosure.strip()
        or "Сервис может получить вознаграждение за переход."
    )


def _public_match_reasons(reasons: list[str], *, purpose_match: bool = False) -> list[str]:
    public: list[str] = []
    if "amount" in reasons and "term" in reasons:
        public.append("Подходит по сумме и сроку")
    if "income" in reasons:
        public.append("Совместимо с указанным диапазоном дохода")
    if "pti" in reasons:
        public.append("Платёж укладывается в выбранный ориентир")
    if "employment_type" in reasons:
        public.append("Учитывает указанный тип занятости")
    if purpose_match:
        public.append("Подходит для выбранной цели кредита")
    return public


def _public_warnings(
    warnings: list[str], result: CreditProfileResult
) -> list[str]:
    public: list[str] = []
    if warnings or result.confidence_level.value in {"low", "basic"}:
        public.append("Уверенность ограничена полнотой указанных диапазонов")
    if result.pti_band.value in {"high", "very_high"}:
        public.append("Ориентировочная долговая нагрузка повышена")
    public.append("Без данных БКИ подбор носит предварительный характер")
    public.append("Условия определяет партнёр; финальное решение принимает банк")
    return public


def create_click(session: Session, offer_id: int, payload: ClickRequest) -> ClickResponse:
    if payload.idempotency_key:
        duplicate = session.scalar(
            select(OfferClick).where(OfferClick.idempotency_key == payload.idempotency_key)
        )
        if duplicate is not None:
            if duplicate.offer_id != offer_id or duplicate.profile_id != payload.profile_id:
                raise CommercialConflictError(
                    "Idempotency key is already associated with another click"
                )
            offer = session.get(BankOffer, duplicate.offer_id)
            if offer is None:
                raise CommercialNotFoundError("Offer no longer exists")
            adapter = get_partner_adapter(offer.partner_id)
            return ClickResponse(
                click_id=duplicate.click_id,
                redirect_url=adapter.build_affiliate_url(
                    offer, duplicate.click_id, payload.model_dump()
                ),
                duplicate=True,
            )
    offer = OfferRepository(session).get_active(offer_id)
    if offer is None:
        raise CommercialNotFoundError("Active offer not found")
    profile_event = session.scalar(
        select(CreditProfileEvent).where(CreditProfileEvent.profile_id == payload.profile_id)
    )
    if profile_event is None:
        raise CommercialNotFoundError("Profile not found")
    click_id = str(uuid4())
    adapter = get_partner_adapter(offer.partner_id)
    redirect_url = adapter.build_affiliate_url(offer, click_id, payload.model_dump())
    impression = session.scalar(
        select(OfferImpression)
        .where(
            OfferImpression.profile_id == payload.profile_id,
            OfferImpression.offer_id == offer_id,
        )
        .order_by(OfferImpression.shown_at.desc())
    )
    experiment_variant = impression.experiment_variant if impression else "rules_v1"
    session.add(
        OfferClick(
            click_id=click_id,
            idempotency_key=payload.idempotency_key,
            anonymous_session_id=profile_event.anonymous_session_id,
            profile_id=payload.profile_id,
            offer_id=offer_id,
            redirect_url_hash=hashlib.sha256(redirect_url.encode()).hexdigest(),
            utm_source=payload.utm_source,
            utm_medium=payload.utm_medium,
            utm_campaign=payload.utm_campaign,
            experiment_variant=experiment_variant,
        )
    )
    session.commit()
    return ClickResponse(click_id=click_id, redirect_url=redirect_url, duplicate=False)


def canonical_postback_bytes(payload: PartnerPostbackRequest) -> bytes:
    return canonical_payload_bytes(payload.model_dump(mode="json", exclude_none=True))


def validate_postback_signature(payload: PartnerPostbackRequest, signature: str) -> bool:
    try:
        adapter = get_partner_adapter(payload.partner_id)
    except ValueError:
        return False
    return adapter.verify_postback(
        PartnerPostbackEnvelope(
            payload=payload.model_dump(mode="json", exclude_none=True),
            signature=signature,
        )
    )


def record_postback(
    session: Session,
    payload: PartnerPostbackRequest,
) -> PartnerPostbackResponse:
    existing = session.scalar(
        select(PartnerPostback).where(
            (PartnerPostback.postback_id == payload.postback_id)
            | (
                (PartnerPostback.click_id == payload.click_id)
                & (PartnerPostback.status == payload.status.value)
            )
        )
    )
    if existing is not None:
        if existing.click_id != payload.click_id or existing.status != payload.status.value:
            raise CommercialConflictError(
                "postback_id is already associated with another outcome"
            )
        return PartnerPostbackResponse(
            postback_id=existing.postback_id,
            accepted=True,
            duplicate=True,
        )
    click = session.scalar(select(OfferClick).where(OfferClick.click_id == payload.click_id))
    if click is None:
        raise CommercialNotFoundError("Click not found")
    offer = session.get(BankOffer, click.offer_id)
    if offer is None or offer.partner_id != payload.partner_id:
        raise CommercialConflictError("Postback partner does not match the clicked offer")
    adapter = get_partner_adapter(payload.partner_id)
    normalized = adapter.normalize_postback(
        payload.model_dump(mode="json", exclude_none=True)
    )
    raw_hash = hashlib.sha256(canonical_postback_bytes(payload)).hexdigest()
    session.add(
        PartnerPostback(
            postback_id=normalized.postback_id,
            click_id=normalized.click_id,
            offer_id=click.offer_id,
            status=normalized.status,
            approved_amount_band=normalized.approved_amount_band,
            issued_amount_band=normalized.issued_amount_band,
            commission_amount=normalized.commission_amount,
            raw_payload_hash=raw_hash,
            validation_status="valid",
        )
    )
    session.commit()
    return PartnerPostbackResponse(
        postback_id=payload.postback_id,
        accepted=True,
        duplicate=False,
    )
