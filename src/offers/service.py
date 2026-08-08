from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from secrets import compare_digest
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
from src.offers.eligibility import evaluate_offer_eligibility
from src.offers.ranking import rank_offers
from src.offers.repository import OfferRepository
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


def _session_for_context(session: Session, context: MatchContext | None) -> AnonymousSession | None:
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
    anonymous = _session_for_context(session, context)
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
    repository = OfferRepository(session)
    evaluated = [
        (offer, evaluate_offer_eligibility(result, offer)) for offer in repository.list_active()
    ]
    ranked = rank_offers(result, evaluated, context.model_dump() if context else None)[:limit]
    for item in ranked:
        session.add(
            OfferImpression(
                anonymous_session_id=profile_event.anonymous_session_id,
                profile_id=result.anonymous_profile_id,
                offer_id=item.offer_id,
                rank=item.rank,
                score=item.final_score,
                score_breakdown_json=item.score_breakdown,
            )
        )
    session.commit()
    return OfferMatchResponse(
        profile_result=result,
        offers=ranked,
        disclaimers=STANDARD_DISCLAIMERS,
    )


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
            return ClickResponse(
                click_id=duplicate.click_id,
                redirect_url=offer.affiliate_url_template.format(click_id=duplicate.click_id),
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
    redirect_url = offer.affiliate_url_template.format(click_id=click_id)
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
        )
    )
    session.commit()
    return ClickResponse(click_id=click_id, redirect_url=redirect_url, duplicate=False)


def canonical_postback_bytes(payload: PartnerPostbackRequest) -> bytes:
    return json.dumps(
        payload.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def validate_postback_signature(payload: PartnerPostbackRequest, signature: str) -> bool:
    configured = settings.partner_postback_secret
    if configured is None or not configured.get_secret_value():
        return False
    expected = hmac.new(
        configured.get_secret_value().encode(), canonical_postback_bytes(payload), hashlib.sha256
    ).hexdigest()
    return compare_digest(signature, expected)


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
    raw_hash = hashlib.sha256(canonical_postback_bytes(payload)).hexdigest()
    session.add(
        PartnerPostback(
            postback_id=payload.postback_id,
            click_id=payload.click_id,
            offer_id=click.offer_id,
            status=payload.status.value,
            approved_amount_band=(
                payload.approved_amount_band.value if payload.approved_amount_band else None
            ),
            issued_amount_band=(
                payload.issued_amount_band.value if payload.issued_amount_band else None
            ),
            commission_amount=payload.commission_amount,
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
