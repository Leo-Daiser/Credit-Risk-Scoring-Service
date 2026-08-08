from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.db.models import BankOffer
from src.offers.partners.base import (
    AdDisclosure,
    PartnerAdapter,
    PartnerPostbackEnvelope,
    PartnerPostbackNormalized,
)
from src.offers.partners.signatures import verify_hmac_sha256

STABLE_STATUSES = {
    "application_started",
    "application_submitted",
    "approved",
    "rejected",
    "issued",
    "cancelled",
}


class DemoPartnerAdapter(PartnerAdapter):
    partner_id = "demo"

    def __init__(self, secret: str | None = None):
        self._secret = secret

    def build_affiliate_url(
        self,
        offer: BankOffer,
        click_id: str,
        context: dict[str, str | None] | None,
    ) -> str:
        rendered = offer.affiliate_url_template.format(click_id=click_id)
        parsed = urlsplit(rendered)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Demo affiliate URL must be an absolute HTTP(S) URL")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["click_id"] = click_id
        for key in ("utm_source", "utm_medium", "utm_campaign"):
            value = (context or {}).get(key)
            if value:
                query[key] = value
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))

    def verify_postback(self, request: PartnerPostbackEnvelope) -> bool:
        return verify_hmac_sha256(request.payload, request.signature, self._secret)

    def normalize_postback(self, payload: dict[str, Any]) -> PartnerPostbackNormalized:
        status = str(payload.get("status", "")).lower()
        if status not in STABLE_STATUSES:
            raise ValueError(f"Unsupported demo postback status: {status or '<missing>'}")
        return PartnerPostbackNormalized(
            postback_id=str(payload["postback_id"]),
            click_id=str(payload["click_id"]),
            status=status,
            approved_amount_band=payload.get("approved_amount_band"),
            issued_amount_band=payload.get("issued_amount_band"),
            commission_amount=(
                float(payload["commission_amount"])
                if payload.get("commission_amount") is not None
                else None
            ),
        )

    def get_public_disclosure(self, offer: BankOffer) -> AdDisclosure:
        return AdDisclosure(
            advertiser_name=offer.advertiser_name,
            label=offer.ad_label_text,
            disclaimer=offer.legal_disclaimer,
            demo_only=True,
        )
