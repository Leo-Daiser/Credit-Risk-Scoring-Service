from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import (
    BankOffer,
    CreditProfileEvent,
    OfferClick,
    OfferImpression,
    PartnerPostback,
)

OUTCOME_STATUSES = (
    "application_started",
    "application_submitted",
    "approved",
    "issued",
)


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_offer_ranking_dataset(
    session: Session,
    *,
    output_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    output = Path(output_path or settings.offer_ranking_dataset_path)
    report = Path(report_path or settings.offer_ranking_dataset_report_path)
    impressions = list(session.scalars(select(OfferImpression).order_by(OfferImpression.id)))
    if not impressions:
        result = {
            "status": "insufficient_data",
            "reason": "No offer impressions are available.",
            "rows": 0,
            "output_path": str(output),
        }
        _write_json(report, result)
        return result

    profiles = {
        item.profile_id: item for item in session.scalars(select(CreditProfileEvent))
    }
    offers = {item.id: item for item in session.scalars(select(BankOffer))}
    clicks = list(session.scalars(select(OfferClick)))
    clicks_by_pair: dict[tuple[str, int], list[OfferClick]] = defaultdict(list)
    for click in clicks:
        clicks_by_pair[(click.profile_id, click.offer_id)].append(click)
    outcomes_by_click: dict[str, list[PartnerPostback]] = defaultdict(list)
    for postback in session.scalars(select(PartnerPostback)):
        outcomes_by_click[postback.click_id].append(postback)

    rows: list[dict[str, Any]] = []
    for impression in impressions:
        profile = profiles.get(impression.profile_id)
        offer = offers.get(impression.offer_id)
        if profile is None or offer is None:
            continue
        matching_clicks = clicks_by_pair[(impression.profile_id, impression.offer_id)]
        postbacks = [
            item for click in matching_clicks for item in outcomes_by_click.get(click.click_id, [])
        ]
        statuses = {item.status for item in postbacks}
        commission = sum(float(item.commission_amount or 0) for item in postbacks)
        rows.append(
            {
                "impression_id": impression.id,
                "profile_id": profile.profile_id,
                "offer_id": offer.id,
                "age_band": profile.age_band,
                "region": profile.region or "unknown",
                "income_band": profile.income_band,
                "employment_type": profile.employment_type,
                "credit_history_band": profile.credit_history_band,
                "requested_amount_band": profile.requested_amount_band,
                "term_months": profile.term_months,
                "loan_purpose": profile.loan_purpose,
                "risk_band": profile.risk_band,
                "pti_band": profile.pti_band,
                "affordability_band": profile.affordability_band,
                "data_coverage": profile.data_coverage,
                "product_type": offer.product_type,
                "bank_id": offer.bank_id,
                "offer_priority": offer.priority,
                "rank_shown": impression.rank,
                "rule_score": impression.score,
                "clicked_flag": int(bool(matching_clicks)),
                **{f"{status}_flag": int(status in statuses) for status in OUTCOME_STATUSES},
                "commission_amount": commission,
            }
        )
    if not rows:
        result = {
            "status": "insufficient_data",
            "reason": "Impressions have no matching profile and offer records.",
            "rows": 0,
            "output_path": str(output),
        }
        _write_json(report, result)
        return result
    frame = pd.DataFrame(rows).sort_values("impression_id").reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    result = {
        "status": "ready" if len(frame) >= settings.offer_ranker_min_samples else "insufficient_data",
        "reason": (
            None
            if len(frame) >= settings.offer_ranker_min_samples
            else f"At least {settings.offer_ranker_min_samples} impressions are required for training."
        ),
        "rows": len(frame),
        "unique_impressions": int(frame["impression_id"].nunique()),
        "unique_profiles": int(frame["profile_id"].nunique()),
        "output_path": str(output),
    }
    if result["unique_impressions"] != result["rows"]:
        raise RuntimeError("Dataset join produced duplicate impression rows")
    _write_json(report, result)
    return result
