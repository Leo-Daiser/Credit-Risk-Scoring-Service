from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.db.models import BankOffer


@dataclass(frozen=True)
class PartnerPostbackEnvelope:
    payload: dict[str, Any]
    signature: str


@dataclass(frozen=True)
class PartnerPostbackNormalized:
    postback_id: str
    click_id: str
    status: str
    approved_amount_band: str | None = None
    issued_amount_band: str | None = None
    commission_amount: float | None = None


@dataclass(frozen=True)
class AdDisclosure:
    advertiser_name: str
    label: str
    disclaimer: str
    demo_only: bool


class PartnerAdapter(ABC):
    partner_id: str

    @abstractmethod
    def build_affiliate_url(
        self,
        offer: BankOffer,
        click_id: str,
        context: dict[str, str | None] | None,
    ) -> str: ...

    @abstractmethod
    def verify_postback(self, request: PartnerPostbackEnvelope) -> bool: ...

    @abstractmethod
    def normalize_postback(self, payload: dict[str, Any]) -> PartnerPostbackNormalized: ...

    @abstractmethod
    def get_public_disclosure(self, offer: BankOffer) -> AdDisclosure: ...
