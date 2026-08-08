"""Partner adapters for affiliate redirects and signed outcome postbacks."""

from src.offers.partners.registry import get_partner_adapter

__all__ = ["get_partner_adapter"]
