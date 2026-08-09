"""Validated offer import/export without materializing affiliate secrets."""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import BankOffer
from src.offers.partners.registry import load_partner_config
from src.offers.repository import AGE_ORDER

ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(https?://|bearer\s+|(?:token|secret|api[_-]?key|password)\s*[:=])"
)
LIST_FIELDS = {
    "allowed_age_bands",
    "allowed_regions",
    "allowed_employment_types",
    "allowed_credit_history_bands",
    "risk_band_policy",
    "display_warnings",
}
EXPORT_FIELDS = [
    "bank_id",
    "product_name",
    "product_type",
    "is_active",
    "priority",
    "min_amount",
    "max_amount",
    "min_term_months",
    "max_term_months",
    "allowed_age_bands",
    "allowed_regions",
    "allowed_employment_types",
    "allowed_credit_history_bands",
    "max_pti_band",
    "risk_band_policy",
    "advertiser_name",
    "ad_label_text",
    "erid",
    "legal_disclaimer",
    "full_cost_range_text",
    "compensation_disclosure",
    "partner_terms_url",
    "main_benefit",
    "display_warnings",
    "cta_text",
    "partner_id",
    "affiliate_url_template_key",
    "commission_type",
    "commission_amount",
    "expires_at",
]


class OfferImportValidationError(ValueError):
    """Safe validation error whose message never contains input values."""


class OfferImportRow(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bank_id: str = Field(min_length=1, max_length=64)
    product_name: str = Field(min_length=1, max_length=255)
    product_type: str = Field(min_length=1, max_length=64)
    is_active: bool = True
    priority: int = Field(default=50, ge=0, le=100)
    min_amount: float = Field(gt=0)
    max_amount: float = Field(gt=0)
    min_term_months: int = Field(ge=3)
    max_term_months: int = Field(ge=3)
    allowed_age_bands: list[str]
    allowed_regions: list[str] = Field(default_factory=list)
    allowed_employment_types: list[str]
    allowed_credit_history_bands: list[str]
    max_pti_band: Literal["low", "moderate", "high", "very_high", "unknown"]
    risk_band_policy: list[str]
    advertiser_name: str = Field(min_length=1, max_length=255)
    ad_label_text: str = Field(min_length=1, max_length=255)
    erid: str | None = Field(default=None, max_length=128)
    legal_disclaimer: str = Field(min_length=1)
    full_cost_range_text: str | None = Field(default=None, max_length=1000)
    compensation_disclosure: str = Field(
        default="Сервис может получить вознаграждение за переход.",
        min_length=1,
        max_length=1000,
    )
    partner_terms_url: str | None = Field(default=None, max_length=1000)
    main_benefit: str | None = Field(default=None, max_length=255)
    display_warnings: list[str] = Field(default_factory=list)
    cta_text: Literal[
        "Посмотреть условия", "Перейти к предложению", "Продолжить у партнёра"
    ] = "Посмотреть условия"
    partner_id: str = Field(min_length=1, max_length=64)
    affiliate_url_template_key: str | None = Field(default=None, max_length=128)
    commission_type: Literal["none", "fixed", "percent"] = "none"
    commission_amount: float | None = Field(default=None, ge=0)
    expires_at: datetime | None = None

    @field_validator(*LIST_FIELDS)
    @classmethod
    def require_non_empty_members(cls, value: list[str], info) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if info.field_name not in {"allowed_regions", "display_warnings"} and not cleaned:
            raise ValueError("list must not be empty")
        return sorted(set(cleaned))

    @model_validator(mode="after")
    def validate_ranges_and_disclosure(self) -> OfferImportRow:
        if self.max_amount < self.min_amount:
            raise ValueError("invalid amount range")
        if self.max_term_months < self.min_term_months:
            raise ValueError("invalid term range")
        if any(value not in AGE_ORDER for value in self.allowed_age_bands):
            raise ValueError("invalid age band")
        if self.is_active and self.expires_at is not None:
            expires = self.expires_at
            if expires.tzinfo is not None:
                expires = expires.astimezone(UTC).replace(tzinfo=None)
            if expires <= datetime.now(UTC).replace(tzinfo=None):
                raise ValueError("active offer is expired")
        if self.partner_id != "demo" and self.is_active and not self.affiliate_url_template_key:
            raise ValueError("active real offer requires affiliate_url_template_key")
        if self.partner_id != "demo" and self.is_active and not self.partner_terms_url:
            raise ValueError("active real offer requires partner_terms_url")
        if self.affiliate_url_template_key and not ENV_KEY_PATTERN.fullmatch(
            self.affiliate_url_template_key
        ):
            raise ValueError("affiliate_url_template_key must be an environment key")
        if self.commission_type == "none" and self.commission_amount not in {None, 0}:
            raise ValueError("commission amount conflicts with commission type")
        return self

    @property
    def identity(self) -> tuple[str, str]:
        return self.bank_id, self.product_name


class OfferImportReport(BaseModel):
    path: str
    mode: Literal["dry_run", "apply"]
    rows: int
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    warnings: list[str] = Field(default_factory=list)


def _parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None or str(value).strip() == "":
        return []
    text = str(value).strip()
    if text.startswith("["):
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError
        return [str(item) for item in parsed]
    separator = "|" if "|" in text else ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def _load_rows(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise OfferImportValidationError("Import file does not exist")
    try:
        if source.suffix.lower() in {".yaml", ".yml"}:
            loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded = loaded.get("offers")
            if not isinstance(loaded, list):
                raise OfferImportValidationError("YAML must contain an offers list")
            rows = [dict(item) for item in loaded if isinstance(item, dict)]
            if len(rows) != len(loaded):
                raise OfferImportValidationError("Every YAML offer must be a mapping")
            return rows
        if source.suffix.lower() == ".csv":
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                return [dict(row) for row in csv.DictReader(stream)]
    except OfferImportValidationError:
        raise
    except Exception as exc:
        raise OfferImportValidationError("Import file cannot be parsed safely") from exc
    raise OfferImportValidationError("Only .yaml, .yml, and .csv files are supported")


def _validate_no_secret_material(row: dict[str, Any], index: int) -> None:
    forbidden_fields = {
        "affiliate_url",
        "affiliate_url_template",
        "affiliate_token",
        "partner_token",
        "secret",
        "api_key",
    }
    if forbidden_fields.intersection(row):
        raise OfferImportValidationError(f"Row {index}: secret or URL field is forbidden")
    terms_url = row.get("partner_terms_url")
    if terms_url:
        parsed = urlsplit(str(terms_url))
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise OfferImportValidationError(
                f"Row {index}: partner terms URL must be public HTTPS without parameters"
            )
    for key, value in row.items():
        if key == "partner_terms_url":
            continue
        values = value if isinstance(value, list) else [value]
        if any(SENSITIVE_TEXT_PATTERN.search(str(item)) for item in values if item is not None):
            raise OfferImportValidationError(f"Row {index}: URL or secret-like value is forbidden")


def _normalize_row(raw: dict[str, Any], index: int) -> OfferImportRow:
    _validate_no_secret_material(raw, index)
    normalized = dict(raw)
    for field in LIST_FIELDS:
        if field in normalized:
            try:
                normalized[field] = _parse_list(normalized[field])
            except Exception as exc:
                raise OfferImportValidationError(f"Row {index}: invalid list field {field}") from exc
    for nullable in (
        "erid",
        "affiliate_url_template_key",
        "commission_amount",
        "expires_at",
        "full_cost_range_text",
        "partner_terms_url",
        "main_benefit",
    ):
        if normalized.get(nullable) == "":
            normalized[nullable] = None
    try:
        return OfferImportRow.model_validate(normalized)
    except ValidationError as exc:
        fields = sorted({str(error["loc"][0]) for error in exc.errors() if error["loc"]})
        suffix = ", ".join(fields) if fields else "row"
        raise OfferImportValidationError(f"Row {index}: validation failed for {suffix}") from exc


def _validate_partner_environment(rows: list[OfferImportRow]) -> list[str]:
    partners = load_partner_config().get("partners", {})
    warnings: list[str] = []
    for row in rows:
        config = partners.get(row.partner_id)
        if not isinstance(config, dict):
            raise OfferImportValidationError(f"Partner is not registered: {row.partner_id}")
        if row.partner_id != "demo" and row.is_active and not config.get("enabled", False):
            raise OfferImportValidationError(f"Active offer uses disabled partner: {row.partner_id}")
        if row.partner_id != "demo" and row.is_active and config.get("adapter") != "env_template":
            raise OfferImportValidationError(
                f"Active partner {row.partner_id} must use the env_template adapter"
            )
        if row.partner_id != "demo" and config.get("enabled", False):
            secret_env = str(config.get("secret_env", "")).strip()
            if not secret_env or not os.getenv(secret_env):
                raise OfferImportValidationError(
                    f"Enabled partner {row.partner_id} requires configured secret environment"
                )
        if row.affiliate_url_template_key:
            template = os.getenv(row.affiliate_url_template_key)
            if row.is_active and row.partner_id != "demo" and not template:
                raise OfferImportValidationError(
                    f"Active offer {row.bank_id}/{row.product_name} requires affiliate template env"
                )
            if template:
                parsed = urlsplit(template.replace("{click_id}", "test-click"))
                if parsed.scheme not in {"http", "https"} or not parsed.netloc or "{click_id}" not in template:
                    raise OfferImportValidationError(
                        f"Affiliate template env for {row.bank_id}/{row.product_name} is invalid"
                    )
        elif row.partner_id == "demo":
            warnings.append(f"{row.bank_id}/{row.product_name}: demo placeholder URL will be used")
    return sorted(set(warnings))


def load_and_validate_offers(path: str | Path) -> tuple[list[OfferImportRow], list[str]]:
    raw_rows = _load_rows(path)
    if not raw_rows:
        raise OfferImportValidationError("Import file contains no offers")
    rows = [_normalize_row(row, index) for index, row in enumerate(raw_rows, start=1)]
    identities = [row.identity for row in rows]
    if len(identities) != len(set(identities)):
        raise OfferImportValidationError("Duplicate bank_id/product_name identifiers in import")
    return rows, _validate_partner_environment(rows)


def _database_values(row: OfferImportRow) -> dict[str, Any]:
    data = row.model_dump()
    age_bands = data["allowed_age_bands"]
    data.update(
        min_age_band=min(age_bands, key=AGE_ORDER.index),
        max_age_band=max(age_bands, key=AGE_ORDER.index),
        min_income_band="unknown",
        affiliate_url_template=(
            f"env://{row.affiliate_url_template_key}"
            if row.affiliate_url_template_key
            else f"https://example.invalid/{row.bank_id}?click_id={{click_id}}"
        ),
    )
    return data


def import_offers(session: Session, path: str | Path, *, apply: bool) -> OfferImportReport:
    rows, warnings = load_and_validate_offers(path)
    report = OfferImportReport(
        path=str(Path(path)),
        mode="apply" if apply else "dry_run",
        rows=len(rows),
        warnings=warnings,
    )
    if not apply:
        return report
    for row in sorted(rows, key=lambda item: item.identity):
        existing = session.scalar(
            select(BankOffer).where(
                BankOffer.bank_id == row.bank_id,
                BankOffer.product_name == row.product_name,
            )
        )
        values = _database_values(row)
        if existing is None:
            session.add(BankOffer(**values))
            report.created += 1
            continue
        changed = False
        for field, value in values.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        if changed:
            report.updated += 1
        else:
            report.unchanged += 1
    session.commit()
    return report


def export_offers(session: Session, path: str | Path) -> int:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    offers = list(session.scalars(select(BankOffer).order_by(BankOffer.id)))
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        for offer in offers:
            row: dict[str, Any] = {}
            for field in EXPORT_FIELDS:
                value = getattr(offer, field)
                if field in LIST_FIELDS:
                    value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                elif isinstance(value, datetime):
                    value = value.isoformat()
                row[field] = value
            writer.writerow(row)
    return len(offers)
