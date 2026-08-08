from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import BankOffer

DEFAULT_CONFIG_PATH = Path("configs/offers.yaml")
AGE_ORDER = ["18_21", "22_30", "31_45", "46_60", "60_plus"]


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
        statement = (
            select(BankOffer)
            .where(
                BankOffer.is_active.is_(True),
                (BankOffer.expires_at.is_(None))
                | (BankOffer.expires_at > datetime.now(UTC).replace(tzinfo=None)),
            )
            .order_by(BankOffer.priority.desc(), BankOffer.id.asc())
        )
        return list(self.session.scalars(statement))

    def get_active(self, offer_id: int) -> BankOffer | None:
        statement = select(BankOffer).where(
            BankOffer.id == offer_id,
            BankOffer.is_active.is_(True),
            (BankOffer.expires_at.is_(None))
            | (BankOffer.expires_at > datetime.now(UTC).replace(tzinfo=None)),
        )
        return self.session.scalar(statement)

    def seed_demo(self, config_path: str | Path = DEFAULT_CONFIG_PATH) -> int:
        config = load_offer_config(config_path)
        created = 0
        for configured_item in config.get("demo_offers", []):
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
            existing = self.session.scalar(
                select(BankOffer).where(
                    BankOffer.bank_id == item["bank_id"],
                    BankOffer.product_name == item["product_name"],
                )
            )
            if existing is not None:
                continue
            self.session.add(BankOffer(is_active=True, erid=None, **item))
            created += 1
        self.session.commit()
        return created
