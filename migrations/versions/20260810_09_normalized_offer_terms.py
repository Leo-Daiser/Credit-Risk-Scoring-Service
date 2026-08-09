"""Add provider identity and offer-specific financial terms."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_09"
down_revision: str | None = "20260809_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_offers",
        sa.Column("provider_id", sa.String(length=64), nullable=False, server_default="demo"),
    )
    op.add_column(
        "bank_offers", sa.Column("provider_offer_id", sa.String(length=128), nullable=True)
    )
    op.add_column("bank_offers", sa.Column("annual_rate_min", sa.Float(), nullable=True))
    op.add_column("bank_offers", sa.Column("annual_rate_max", sa.Float(), nullable=True))
    op.add_column("bank_offers", sa.Column("fee_disclosure", sa.Text(), nullable=True))
    op.add_column("bank_offers", sa.Column("insurance_disclosure", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_bank_offers_provider_offer",
        "bank_offers",
        ["provider_id", "provider_offer_id"],
    )
    op.create_check_constraint(
        "ck_bank_offers_rate_min",
        "bank_offers",
        "annual_rate_min IS NULL OR (annual_rate_min >= 0 AND annual_rate_min <= 100)",
    )
    op.create_check_constraint(
        "ck_bank_offers_rate_max",
        "bank_offers",
        "annual_rate_max IS NULL OR (annual_rate_max >= annual_rate_min AND annual_rate_max <= 100)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bank_offers_rate_max", "bank_offers", type_="check")
    op.drop_constraint("ck_bank_offers_rate_min", "bank_offers", type_="check")
    op.drop_constraint("uq_bank_offers_provider_offer", "bank_offers", type_="unique")
    op.drop_column("bank_offers", "insurance_disclosure")
    op.drop_column("bank_offers", "fee_disclosure")
    op.drop_column("bank_offers", "annual_rate_max")
    op.drop_column("bank_offers", "annual_rate_min")
    op.drop_column("bank_offers", "provider_offer_id")
    op.drop_column("bank_offers", "provider_id")
