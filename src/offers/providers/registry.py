from __future__ import annotations

from sqlalchemy.orm import Session

from src.offers.providers.base import OfferProvider
from src.offers.providers.demo import DemoOfferProvider


def get_offer_provider(session: Session) -> OfferProvider:
    """Return the configured normalized catalog provider.

    External network providers intentionally remain unregistered until their
    data, authentication, disclosure, and retry contracts are implemented.
    """
    return DemoOfferProvider(session)
