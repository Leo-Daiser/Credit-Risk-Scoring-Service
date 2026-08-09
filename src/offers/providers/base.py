from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.db.models import BankOffer


@dataclass(frozen=True)
class NormalizedOffer:
    """Provider-neutral catalog record used by matching and calculations."""

    provider_id: str
    provider_offer_id: str
    record: BankOffer


class OfferProvider(ABC):
    provider_id: str

    @abstractmethod
    def list_offers(self) -> list[NormalizedOffer]: ...

    @abstractmethod
    def get_offer(self, offer_id: int) -> NormalizedOffer | None: ...

    @abstractmethod
    def refresh(self) -> dict[str, Any]: ...

    @abstractmethod
    def health(self) -> dict[str, Any]: ...
