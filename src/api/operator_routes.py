from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.dependencies import require_local_demo_operator_api_key, require_operator_api_key
from src.db.session import get_db
from src.offers.analytics import CommercialAnalyticsService, recent_event_debug
from src.offers.management import (
    OfferManagementConflictError,
    OfferManagementNotFoundError,
    OfferManagementValidationError,
    create_operator_offer,
    deactivate_operator_offer,
    get_operator_offer,
    list_operator_offers,
    patch_operator_offer,
    validate_operator_offer,
)
from src.offers.operator_offer_schemas import (
    OfferPatch,
    OfferValidationResult,
    OfferWritable,
    OperatorOfferListResponse,
    OperatorOfferResponse,
)
from src.offers.operator_schemas import (
    CommercialAnalyticsResponse,
    EventDebugResponse,
    OfferQualityReport,
    SegmentOpportunityResponse,
)
from src.offers.quality import build_offer_quality_report
from src.offers.segment_analysis import analyze_segment_opportunities

router = APIRouter(
    prefix="/v1",
    tags=["commercial-operator"],
    dependencies=[Depends(require_operator_api_key)],
)


def _validate_days(days: int) -> int:
    if days not in {7, 30, 90}:
        raise HTTPException(status_code=422, detail="days must be one of: 7, 30, 90")
    return days


def _management_error(exc: ValueError) -> HTTPException:
    if isinstance(exc, OfferManagementNotFoundError):
        return HTTPException(status_code=404, detail="Offer not found.")
    if isinstance(exc, OfferManagementConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, OfferManagementValidationError):
        return HTTPException(
            status_code=422,
            detail={"message": "Offer validation failed.", "errors": exc.errors},
        )
    return HTTPException(status_code=422, detail="Offer operation failed.")


@router.get(
    "/operator/offers",
    response_model=OperatorOfferListResponse,
    dependencies=[Depends(require_local_demo_operator_api_key)],
)
def operator_offer_list(
    active: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=128),
    session: Session = Depends(get_db),
) -> OperatorOfferListResponse:
    return list_operator_offers(session, active=active, search=search)


@router.get(
    "/operator/offers/{offer_id}",
    response_model=OperatorOfferResponse,
    dependencies=[Depends(require_local_demo_operator_api_key)],
)
def operator_offer_detail(
    offer_id: int,
    session: Session = Depends(get_db),
) -> OperatorOfferResponse:
    try:
        return get_operator_offer(session, offer_id)
    except ValueError as exc:
        raise _management_error(exc) from exc


@router.post(
    "/operator/offers",
    response_model=OperatorOfferResponse,
    status_code=201,
    dependencies=[Depends(require_local_demo_operator_api_key)],
)
def operator_offer_create(
    payload: OfferWritable,
    session: Session = Depends(get_db),
) -> OperatorOfferResponse:
    try:
        return create_operator_offer(session, payload)
    except ValueError as exc:
        raise _management_error(exc) from exc


@router.patch(
    "/operator/offers/{offer_id}",
    response_model=OperatorOfferResponse,
    dependencies=[Depends(require_local_demo_operator_api_key)],
)
def operator_offer_patch(
    offer_id: int,
    payload: OfferPatch,
    session: Session = Depends(get_db),
) -> OperatorOfferResponse:
    try:
        return patch_operator_offer(session, offer_id, payload)
    except ValueError as exc:
        raise _management_error(exc) from exc


@router.post(
    "/operator/offers/{offer_id}/deactivate",
    response_model=OperatorOfferResponse,
    dependencies=[Depends(require_local_demo_operator_api_key)],
)
def operator_offer_deactivate(
    offer_id: int,
    session: Session = Depends(get_db),
) -> OperatorOfferResponse:
    try:
        return deactivate_operator_offer(session, offer_id)
    except ValueError as exc:
        raise _management_error(exc) from exc


@router.post(
    "/operator/offers/{offer_id}/validate",
    response_model=OfferValidationResult,
    dependencies=[Depends(require_local_demo_operator_api_key)],
)
def operator_offer_validate(
    offer_id: int,
    payload: OfferPatch | None = None,
    session: Session = Depends(get_db),
) -> OfferValidationResult:
    try:
        return validate_operator_offer(session, offer_id, payload)
    except ValueError as exc:
        raise _management_error(exc) from exc


@router.get(
    "/analytics/commercial-summary",
    response_model=CommercialAnalyticsResponse,
)
def commercial_summary(
    days: int = Query(default=30),
    offer_id: int | None = Query(default=None, ge=1),
    risk_band: str | None = Query(default=None, max_length=32),
    pti_band: str | None = Query(default=None, max_length=32),
    session: Session = Depends(get_db),
) -> CommercialAnalyticsResponse:
    return CommercialAnalyticsService(session).summary(
        days=_validate_days(days),
        offer_id=offer_id,
        risk_band=risk_band,
        pti_band=pti_band,
    )


@router.get("/offers/quality-report", response_model=OfferQualityReport)
def offer_quality_report(
    days: int = Query(default=30),
    session: Session = Depends(get_db),
) -> OfferQualityReport:
    return build_offer_quality_report(session, days=_validate_days(days))


@router.get(
    "/analytics/segment-opportunities",
    response_model=SegmentOpportunityResponse,
)
def segment_opportunities(
    days: int = Query(default=30),
    session: Session = Depends(get_db),
) -> SegmentOpportunityResponse:
    return analyze_segment_opportunities(session, days=_validate_days(days))


@router.get("/analytics/event-debug", response_model=EventDebugResponse)
def event_debug(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> EventDebugResponse:
    return recent_event_debug(session, limit=limit)
