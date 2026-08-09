from __future__ import annotations

import os
from datetime import UTC
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.db.models import BankOffer
from src.offers.operator_offer_schemas import (
    OfferPatch,
    OfferValidationResult,
    OfferWritable,
    OperatorOfferListResponse,
    OperatorOfferResponse,
)
from src.offers.partners.registry import load_partner_config
from src.offers.quality import build_offer_quality_report
from src.offers.repository import AGE_ORDER


class OfferManagementError(ValueError):
    pass


class OfferManagementNotFoundError(OfferManagementError):
    pass


class OfferManagementConflictError(OfferManagementError):
    pass


class OfferManagementValidationError(OfferManagementError):
    def __init__(self, errors: list[str]):
        super().__init__("Offer validation failed")
        self.errors = errors


def _safe_validation_errors(exc: ValidationError) -> list[str]:
    fields = sorted(
        {
            str(error["loc"][0]) if error.get("loc") else "offer"
            for error in exc.errors()
        }
    )
    return [f"invalid_{field}" for field in fields]


def _partner_validation(candidate: OfferWritable) -> OfferValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        partners = load_partner_config().get("partners", {})
    except ValueError:
        return OfferValidationResult(valid=False, errors=["partner_config_unavailable"])
    partner = partners.get(candidate.partner_id)
    if not isinstance(partner, dict):
        errors.append("partner_not_registered")
    elif candidate.partner_id == "demo":
        warnings.append("demo_only")
        if not partner.get("enabled", False):
            errors.append("demo_partner_disabled")
    else:
        if candidate.is_active and not partner.get("enabled", False):
            errors.append("active_partner_disabled")
        if candidate.is_active and partner.get("adapter") != "env_template":
            errors.append("real_partner_adapter_invalid")
        if partner.get("enabled", False):
            secret_env = str(partner.get("secret_env", "")).strip()
            if not secret_env or not os.getenv(secret_env):
                errors.append("partner_secret_environment_missing")
        if candidate.is_active and candidate.affiliate_url_template_key:
            template = os.getenv(candidate.affiliate_url_template_key)
            if not template:
                errors.append("affiliate_template_environment_missing")
            elif "{click_id}" not in template:
                errors.append("affiliate_template_click_id_missing")
    if candidate.is_active and not candidate.erid:
        warnings.append("erid_not_configured")
    if candidate.is_active and candidate.partner_id == "demo":
        warnings.append("demo_link")
    return OfferValidationResult(
        valid=not errors,
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
    )


def validate_offer_payload(data: dict[str, Any]) -> tuple[OfferWritable | None, OfferValidationResult]:
    try:
        candidate = OfferWritable.model_validate(data)
    except ValidationError as exc:
        errors = _safe_validation_errors(exc)
        return None, OfferValidationResult(valid=False, errors=errors)
    return candidate, _partner_validation(candidate)


def _offer_payload(offer: BankOffer) -> dict[str, Any]:
    return {
        "provider_id": offer.provider_id,
        "provider_offer_id": offer.provider_offer_id,
        "bank_id": offer.bank_id,
        "product_name": offer.product_name,
        "product_type": offer.product_type,
        "is_active": offer.is_active,
        "priority": offer.priority,
        "min_amount": offer.min_amount,
        "max_amount": offer.max_amount,
        "min_term_months": offer.min_term_months,
        "max_term_months": offer.max_term_months,
        "annual_rate_min": offer.annual_rate_min,
        "annual_rate_max": offer.annual_rate_max,
        "fee_disclosure": offer.fee_disclosure,
        "insurance_disclosure": offer.insurance_disclosure,
        "allowed_age_bands": offer.allowed_age_bands,
        "min_income_band": offer.min_income_band,
        "allowed_regions": offer.allowed_regions,
        "allowed_employment_types": offer.allowed_employment_types,
        "allowed_credit_history_bands": offer.allowed_credit_history_bands,
        "max_pti_band": offer.max_pti_band,
        "risk_band_policy": offer.risk_band_policy,
        "advertiser_name": offer.advertiser_name,
        "ad_label_text": offer.ad_label_text,
        "erid": offer.erid,
        "legal_disclaimer": offer.legal_disclaimer,
        "full_cost_range_text": offer.full_cost_range_text,
        "compensation_disclosure": offer.compensation_disclosure,
        "partner_terms_url": offer.partner_terms_url,
        "main_benefit": offer.main_benefit,
        "display_warnings": offer.display_warnings,
        "cta_text": offer.cta_text,
        "partner_id": offer.partner_id,
        "affiliate_url_template_key": offer.affiliate_url_template_key,
        "commission_type": offer.commission_type,
        "commission_amount": (
            float(offer.commission_amount)
            if isinstance(offer.commission_amount, Decimal)
            else offer.commission_amount
        ),
        "expires_at": offer.expires_at,
    }


def _database_values(candidate: OfferWritable) -> dict[str, Any]:
    values = candidate.model_dump()
    if values["expires_at"] is not None and values["expires_at"].tzinfo is not None:
        values["expires_at"] = values["expires_at"].astimezone(UTC).replace(tzinfo=None)
    age_bands = candidate.allowed_age_bands
    values.update(
        min_age_band=min(age_bands, key=AGE_ORDER.index),
        max_age_band=max(age_bands, key=AGE_ORDER.index),
        affiliate_url_template=(
            f"env://{candidate.affiliate_url_template_key}"
            if candidate.affiliate_url_template_key
            else f"https://example.invalid/{candidate.bank_id}?click_id={{click_id}}"
        ),
    )
    return values


def _require_valid(data: dict[str, Any]) -> OfferWritable:
    candidate, result = validate_offer_payload(data)
    if candidate is None or not result.valid:
        raise OfferManagementValidationError(result.errors)
    return candidate


def _get_offer(session: Session, offer_id: int) -> BankOffer:
    offer = session.get(BankOffer, offer_id)
    if offer is None:
        raise OfferManagementNotFoundError("Offer not found")
    return offer


def _ensure_unique_identity(
    session: Session, candidate: OfferWritable, *, exclude_id: int | None = None
) -> None:
    statement = select(BankOffer.id).where(
        BankOffer.bank_id == candidate.bank_id,
        BankOffer.product_name == candidate.product_name,
    )
    if exclude_id is not None:
        statement = statement.where(BankOffer.id != exclude_id)
    if session.scalar(statement) is not None:
        raise OfferManagementConflictError("Offer bank/product identity already exists")


def _response(
    offer: BankOffer,
    *,
    validation: OfferValidationResult,
    quality_flags: list[str],
    recommendation: str,
) -> OperatorOfferResponse:
    return OperatorOfferResponse(
        id=offer.id,
        created_at=offer.created_at,
        updated_at=offer.updated_at,
        validation_status="valid" if validation.valid else "invalid",
        validation_errors=validation.errors,
        quality_flags=quality_flags,
        quality_recommendation=recommendation,
        **_offer_payload(offer),
    )


def list_operator_offers(
    session: Session,
    *,
    active: bool | None = None,
    search: str | None = None,
) -> OperatorOfferListResponse:
    statement = select(BankOffer)
    if active is not None:
        statement = statement.where(BankOffer.is_active.is_(active))
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(BankOffer.bank_id.ilike(pattern), BankOffer.product_name.ilike(pattern))
        )
    offers = list(
        session.scalars(statement.order_by(BankOffer.priority.desc(), BankOffer.id.asc()))
    )
    quality = build_offer_quality_report(session, days=30)
    quality_map = {item.offer_id: item for item in quality.offers}
    items: list[OperatorOfferResponse] = []
    for offer in offers:
        _, validation = validate_offer_payload(_offer_payload(offer))
        quality_item = quality_map[offer.id]
        items.append(
            _response(
                offer,
                validation=validation,
                quality_flags=quality_item.quality_flags,
                recommendation=quality_item.recommendation,
            )
        )
    return OperatorOfferListResponse(items=items, total=len(items))


def get_operator_offer(session: Session, offer_id: int) -> OperatorOfferResponse:
    offer = _get_offer(session, offer_id)
    report = list_operator_offers(session)
    return next(item for item in report.items if item.id == offer.id)


def create_operator_offer(session: Session, payload: OfferWritable) -> OperatorOfferResponse:
    candidate = _require_valid(payload.model_dump())
    _ensure_unique_identity(session, candidate)
    offer = BankOffer(**_database_values(candidate))
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return get_operator_offer(session, offer.id)


def patch_operator_offer(
    session: Session, offer_id: int, payload: OfferPatch
) -> OperatorOfferResponse:
    offer = _get_offer(session, offer_id)
    merged = {**_offer_payload(offer), **payload.model_dump(exclude_unset=True)}
    candidate = _require_valid(merged)
    _ensure_unique_identity(session, candidate, exclude_id=offer.id)
    for field, value in _database_values(candidate).items():
        setattr(offer, field, value)
    session.commit()
    session.refresh(offer)
    return get_operator_offer(session, offer.id)


def deactivate_operator_offer(session: Session, offer_id: int) -> OperatorOfferResponse:
    offer = _get_offer(session, offer_id)
    offer.is_active = False
    session.commit()
    session.refresh(offer)
    return get_operator_offer(session, offer.id)


def validate_operator_offer(
    session: Session, offer_id: int, payload: OfferPatch | None = None
) -> OfferValidationResult:
    offer = _get_offer(session, offer_id)
    merged = _offer_payload(offer)
    if payload is not None:
        merged.update(payload.model_dump(exclude_unset=True))
    _, result = validate_offer_payload(merged)
    return result
