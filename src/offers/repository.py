from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import BankOffer

DEFAULT_CONFIG_PATH = Path("configs/offers.yaml")
AGE_ORDER = ["18_21", "22_30", "31_45", "46_60", "60_plus"]
LEGACY_DEMO_BANK_IDS = {"demo-a", "demo-b", "demo-c"}


def load_offer_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError("Offer configuration must be a mapping")
    return config


class OfferRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_active(self) -> list[BankOffer]:
        filters = [
            BankOffer.is_active.is_(True),
            (BankOffer.expires_at.is_(None))
            | (BankOffer.expires_at > datetime.now(UTC).replace(tzinfo=None)),
        ]
        if not settings.demo_adapter_allowed:
            filters.append(BankOffer.partner_id != "demo")
        statement = (
            select(BankOffer)
            .where(*filters)
            .order_by(BankOffer.priority.desc(), BankOffer.id.asc())
        )
        return list(self.session.scalars(statement))

    def get_active(self, offer_id: int) -> BankOffer | None:
        filters = [
            BankOffer.id == offer_id,
            BankOffer.is_active.is_(True),
            (BankOffer.expires_at.is_(None))
            | (BankOffer.expires_at > datetime.now(UTC).replace(tzinfo=None)),
        ]
        if not settings.demo_adapter_allowed:
            filters.append(BankOffer.partner_id != "demo")
        statement = select(BankOffer).where(*filters)
        return self.session.scalar(statement)

    def seed_demo(self, config_path: str | Path = DEFAULT_CONFIG_PATH) -> int:
        config = load_offer_config(config_path)
        created = 0
        configured_offers = config.get("demo_offers", [])
        configured_provider_offer_ids = {
            str(item["provider_offer_id"])
            for item in configured_offers
            if item.get("provider_offer_id")
        }
        for configured_item in configured_offers:
            item = dict(configured_item)
            age_bands = item["allowed_age_bands"]
            if not age_bands or any(value not in AGE_ORDER for value in age_bands):
                raise ValueError("Every demo offer must define valid allowed_age_bands")
            if "{click_id}" not in item["affiliate_url_template"]:
                raise ValueError("affiliate_url_template must contain {click_id}")
            if not str(item.get("partner_id", "")).strip():
                raise ValueError("Every offer must define partner_id")
            item["min_age_band"] = min(age_bands, key=AGE_ORDER.index)
            item["max_age_band"] = max(age_bands, key=AGE_ORDER.index)
            existing_items = list(
                self.session.scalars(
                    select(BankOffer)
                    .where(
                        BankOffer.bank_id == item["bank_id"],
                        BankOffer.partner_id == "demo",
                    )
                    .order_by(BankOffer.id.asc())
                )
            )
            existing = next(
                (
                    offer
                    for offer in existing_items
                    if offer.product_name == item["product_name"]
                ),
                existing_items[0] if existing_items else None,
            )
            if existing is None:
                self.session.add(BankOffer(is_active=True, erid=None, **item))
                created += 1
            else:
                for field, value in item.items():
                    setattr(existing, field, value)
                existing.is_active = True
                existing.erid = None
                for duplicate in existing_items:
                    if duplicate.id != existing.id:
                        duplicate.is_active = False

        managed_demo_offers = self.session.scalars(
            select(BankOffer).where(BankOffer.partner_id == "demo")
        )
        for offer in managed_demo_offers:
            is_removed_catalog_offer = (
                offer.provider_id == "demo"
                and offer.provider_offer_id is not None
                and offer.provider_offer_id not in configured_provider_offer_ids
            )
            is_legacy_catalog_offer = offer.bank_id in LEGACY_DEMO_BANK_IDS
            if is_removed_catalog_offer or is_legacy_catalog_offer:
                offer.is_active = False
        self.session.commit()
        return created
