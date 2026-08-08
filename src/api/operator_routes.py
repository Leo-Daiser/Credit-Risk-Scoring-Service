from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.dependencies import require_operator_api_key
from src.db.session import get_db
from src.offers.analytics import CommercialAnalyticsService, recent_event_debug
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
