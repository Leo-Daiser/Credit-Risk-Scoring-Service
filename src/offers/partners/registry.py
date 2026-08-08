from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from src.core.config import settings
from src.db.models import BankOffer
from src.offers.partners.base import PartnerAdapter
from src.offers.partners.demo_partner import DemoPartnerAdapter
from src.offers.partners.env_partner import EnvTemplatePartnerAdapter


def load_partner_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or settings.partner_config_path)
    if not config_path.exists():
        raise ValueError(f"Partner configuration not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict) or not isinstance(config.get("partners"), dict):
        raise ValueError("Partner configuration must contain a partners mapping")
    return config


def get_partner_adapter(
    partner_id: str,
    *,
    config_path: str | Path | None = None,
) -> PartnerAdapter:
    partners = load_partner_config(config_path)["partners"]
    partner = partners.get(partner_id)
    if not isinstance(partner, dict):
        raise ValueError(f"Partner is not registered: {partner_id}")
    if not partner.get("enabled", False):
        raise ValueError(f"Partner is disabled: {partner_id}")
    adapter_name = partner.get("adapter")
    secret_env = str(partner.get("secret_env", "")).strip()
    configured_secret = os.getenv(secret_env) if secret_env else None
    if partner_id == "demo" and settings.partner_postback_secret is not None:
        configured_secret = settings.partner_postback_secret.get_secret_value()
    if adapter_name == "demo":
        return DemoPartnerAdapter(configured_secret)
    if not configured_secret:
        raise ValueError(f"Enabled partner {partner_id} requires secret env {secret_env}")
    if adapter_name == "env_template":
        return EnvTemplatePartnerAdapter(partner_id, configured_secret)
    raise ValueError(f"Partner adapter is not implemented: {adapter_name}")


def resolve_affiliate_template(offer: BankOffer) -> str:
    """Resolve a template at click time without persisting or logging its value."""
    if offer.affiliate_url_template_key:
        template = os.getenv(offer.affiliate_url_template_key)
        if not template:
            raise ValueError("Affiliate template environment value is not configured")
        return template
    return offer.affiliate_url_template
