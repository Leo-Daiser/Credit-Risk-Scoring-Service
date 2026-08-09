from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_optional_public_profile_scoring_service,
    require_local_demo_operator_api_key,
)
from src.api.metrics import (
    COMMERCIAL_PTI_BANDS,
    COMMERCIAL_RISK_BANDS,
    ELIGIBLE_OFFERS,
    NO_ELIGIBLE_OFFERS,
    OFFER_MATCH_REQUESTS,
    OFFER_POSTBACKS,
    OFFER_RANKER_MODE,
    POSTBACK_SIGNATURE_FAILURES,
    REDIRECT_FAILURES,
    record_offer_click,
    record_offer_impression,
)
from src.api.rate_limit import rate_limit, record_invalid_postback
from src.api.schemas import RuntimeStatusResponse
from src.core.config import settings
from src.core.runtime import build_runtime_status
from src.db.models import BankOffer, OfferClick
from src.db.session import get_db
from src.offers.analytics import record_funnel_event
from src.offers.repository import OfferRepository
from src.offers.schemas import (
    ClickRequest,
    ClickResponse,
    CreditProfileInput,
    CreditProfileResult,
    MatchContext,
    OfferMatchRequest,
    OfferMatchResponse,
    OfferPublic,
    PartnerPostbackRequest,
    PartnerPostbackResponse,
    PublicAnalyticsEventRequest,
    PublicAnalyticsEventResponse,
)
from src.offers.service import (
    CommercialConflictError,
    CommercialNotFoundError,
    build_profile_result,
    create_click,
    ensure_anonymous_session,
    match_offers,
    record_postback,
    validate_postback_signature,
)
from src.public_profile.service import PublicProfileScoringService

router = APIRouter(prefix="/v1", tags=["commercial"])
logger = logging.getLogger(__name__)


@router.get(
    "/runtime/status",
    response_model=RuntimeStatusResponse,
    dependencies=[Depends(require_local_demo_operator_api_key)],
)
def runtime_status(session: Session = Depends(get_db)) -> RuntimeStatusResponse:
    return RuntimeStatusResponse.model_validate(build_runtime_status(session))


@router.post(
    "/analytics/public-event",
    response_model=PublicAnalyticsEventResponse,
    dependencies=[Depends(rate_limit("public_event"))],
)
def public_analytics_event(
    payload: PublicAnalyticsEventRequest,
    session: Session = Depends(get_db),
) -> PublicAnalyticsEventResponse:
    """Record only allowlisted, non-financial public funnel metadata."""
    anonymous = ensure_anonymous_session(
        session,
        MatchContext(anonymous_session_id=payload.anonymous_session_id)
        if payload.anonymous_session_id
        else None,
    )
    record_funnel_event(
        session,
        payload.event_type,
        anonymous_session_id=anonymous.id if anonymous else None,
        risk_band=payload.profile_band,
        pti_band=payload.pti_band,
        event_value=": ".join(
            value
            for value in (payload.page, payload.scenario_type, payload.offer_position)
            if value
        ),
    )
    session.commit()
    return PublicAnalyticsEventResponse()


@router.post(
    "/profile/score",
    response_model=CreditProfileResult,
    dependencies=[Depends(rate_limit("profile_score"))],
)
def score_profile(
    payload: CreditProfileInput,
    session: Session = Depends(get_db),
    service: PublicProfileScoringService | None = Depends(
        get_optional_public_profile_scoring_service
    ),
) -> CreditProfileResult:
    result = build_profile_result(payload, service)
    for event_type in ("profile_started", "profile_completed", "profile_scored"):
        record_funnel_event(
            session,
            event_type,
            profile_id=result.anonymous_profile_id,
            risk_band=result.risk_band,
            pti_band=result.pti_band.value,
        )
    session.commit()
    COMMERCIAL_RISK_BANDS.labels(result.risk_band).inc()
    COMMERCIAL_PTI_BANDS.labels(result.pti_band.value).inc()
    logger.info(
        "commercial_profile_scored",
        extra={
            "profile_id": result.anonymous_profile_id,
            "risk_band": result.risk_band,
            "event_type": "profile_scored",
        },
    )
    return result


@router.post(
    "/offers/match",
    response_model=OfferMatchResponse,
    dependencies=[Depends(rate_limit("offer_match"))],
)
def match(
    payload: OfferMatchRequest,
    session: Session = Depends(get_db),
    service: PublicProfileScoringService | None = Depends(
        get_optional_public_profile_scoring_service
    ),
) -> OfferMatchResponse:
    result = match_offers(session, payload.profile, payload.limit, payload.context, service)
    OFFER_MATCH_REQUESTS.inc()
    ELIGIBLE_OFFERS.observe(len(result.offers))
    OFFER_RANKER_MODE.labels(settings.offer_ranker_mode).set(1)
    if not result.offers:
        NO_ELIGIBLE_OFFERS.inc()
    for offer in result.offers:
        record_offer_impression(offer.offer_id)
    COMMERCIAL_RISK_BANDS.labels(result.profile_result.risk_band).inc()
    COMMERCIAL_PTI_BANDS.labels(result.profile_result.pti_band.value).inc()
    logger.info(
        "offer_match_completed",
        extra={
            "profile_id": result.profile_result.anonymous_profile_id,
            "ranker_mode": settings.offer_ranker_mode,
            "event_type": "offer_match",
        },
    )
    return result


@router.get(
    "/offers",
    response_model=list[OfferPublic],
    dependencies=[Depends(require_local_demo_operator_api_key)],
)
def list_offers(session: Session = Depends(get_db)) -> list[BankOffer]:
    return OfferRepository(session).list_active()


@router.post(
    "/offers/{offer_id}/click",
    response_model=ClickResponse,
    dependencies=[Depends(rate_limit("offer_click"))],
)
def click_offer(
    offer_id: int,
    payload: ClickRequest,
    session: Session = Depends(get_db),
) -> ClickResponse:
    try:
        result = create_click(session, offer_id, payload)
    except CommercialConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Переход уже обрабатывается. Обновите страницу и попробуйте снова.",
        ) from exc
    except CommercialNotFoundError as exc:
        REDIRECT_FAILURES.inc()
        record_funnel_event(
            session,
            "partner_redirect_failed",
            profile_id=payload.profile_id,
            offer_id=offer_id,
            event_value="not_available",
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Предложение временно недоступно.",
        ) from exc
    except ValueError as exc:
        REDIRECT_FAILURES.inc()
        record_funnel_event(
            session,
            "partner_redirect_failed",
            profile_id=payload.profile_id,
            offer_id=offer_id,
            event_value="integration_unavailable",
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Переход к партнёру временно недоступен.",
        ) from exc
    if not result.duplicate:
        record_offer_click(offer_id)
    logger.info(
        "offer_click_created",
        extra={
            "profile_id": payload.profile_id,
            "offer_id": offer_id,
            "click_id": result.click_id,
            "event_type": "offer_click",
        },
    )
    return result


@router.post(
    "/partner/postback",
    response_model=PartnerPostbackResponse,
    dependencies=[Depends(rate_limit("partner_postback"))],
)
def partner_postback(
    payload: PartnerPostbackRequest,
    request: Request,
    x_postback_signature: str = Header(default="", alias="X-Postback-Signature"),
    session: Session = Depends(get_db),
) -> PartnerPostbackResponse:
    if not settings.partner_postbacks_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner unavailable.")
    if settings.is_public and payload.partner_id == "demo":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner unavailable.")
    if not validate_postback_signature(payload, x_postback_signature):
        POSTBACK_SIGNATURE_FAILURES.inc()
        record_funnel_event(
            session,
            "partner_postback_received",
            click_id=payload.click_id,
            event_value="invalid",
        )
        session.commit()
        record_invalid_postback(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid postback signature.",
        )
    try:
        result = record_postback(session, payload)
    except CommercialConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CommercialNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not result.duplicate:
        click_offer_id = session.scalar(
            select(OfferClick.offer_id).where(OfferClick.click_id == payload.click_id)
        )
        OFFER_POSTBACKS.labels(str(click_offer_id), payload.status.value).inc()
    logger.info(
        "partner_postback_recorded",
        extra={"click_id": payload.click_id, "event_type": "partner_postback"},
    )
    return result
