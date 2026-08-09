from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.offers.providers.base import NormalizedOffer, OfferProvider
from src.offers.repository import OfferRepository


class DemoOfferProvider(OfferProvider):
    provider_id = "demo"

    def __init__(self, session: Session):
        self.repository = OfferRepository(session)

    def list_offers(self) -> list[NormalizedOffer]:
        return [self._normalize(offer) for offer in self.repository.list_active()]

    def get_offer(self, offer_id: int) -> NormalizedOffer | None:
        offer = self.repository.get_active(offer_id)
        return self._normalize(offer) if offer is not None else None

    def refresh(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "mode": "database_catalog", "changed": 0}

    def health(self) -> dict[str, Any]:
        offers = self.list_offers()
        return {
            "provider_id": self.provider_id,
            "healthy": bool(offers),
            "offer_count": len(offers),
            "external_calls": False,
        }

    def _normalize(self, offer) -> NormalizedOffer:
        return NormalizedOffer(
            provider_id=offer.provider_id or self.provider_id,
            provider_offer_id=offer.provider_offer_id or f"offer-{offer.id}",
            record=offer,
        )
