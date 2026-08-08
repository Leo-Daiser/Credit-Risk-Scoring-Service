from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.dependencies import get_optional_scoring_service, require_api_key
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
from src.core.config import settings
from src.db.models import BankOffer, OfferClick
from src.db.session import get_db
from src.offers.repository import OfferRepository
from src.offers.schemas import (
    ClickRequest,
    ClickResponse,
    CreditProfileInput,
    CreditProfileResult,
    OfferMatchRequest,
    OfferMatchResponse,
    OfferPublic,
    PartnerPostbackRequest,
    PartnerPostbackResponse,
)
from src.offers.service import (
    CommercialConflictError,
    CommercialNotFoundError,
    build_profile_result,
    create_click,
    match_offers,
    record_postback,
    validate_postback_signature,
)
from src.services.scoring import ScoringService

router = APIRouter(prefix="/v1", tags=["commercial"])
logger = logging.getLogger(__name__)


@router.post(
    "/profile/score",
    response_model=CreditProfileResult,
    dependencies=[Depends(require_api_key)],
)
def score_profile(
    payload: CreditProfileInput,
    service: ScoringService | None = Depends(get_optional_scoring_service),
) -> CreditProfileResult:
    result = build_profile_result(payload, service)
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
    dependencies=[Depends(require_api_key)],
)
def match(
    payload: OfferMatchRequest,
    session: Session = Depends(get_db),
    service: ScoringService | None = Depends(get_optional_scoring_service),
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
    dependencies=[Depends(require_api_key)],
)
def list_offers(session: Session = Depends(get_db)) -> list[BankOffer]:
    return OfferRepository(session).list_active()


@router.post(
    "/offers/{offer_id}/click",
    response_model=ClickResponse,
    dependencies=[Depends(require_api_key)],
)
def click_offer(
    offer_id: int,
    payload: ClickRequest,
    session: Session = Depends(get_db),
) -> ClickResponse:
    try:
        result = create_click(session, offer_id, payload)
    except CommercialConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CommercialNotFoundError as exc:
        REDIRECT_FAILURES.inc()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
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


@router.post("/partner/postback", response_model=PartnerPostbackResponse)
def partner_postback(
    payload: PartnerPostbackRequest,
    x_postback_signature: str = Header(default="", alias="X-Postback-Signature"),
    session: Session = Depends(get_db),
) -> PartnerPostbackResponse:
    if not validate_postback_signature(payload, x_postback_signature):
        POSTBACK_SIGNATURE_FAILURES.inc()
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
