"""Add safe affiliate template references and deterministic offer identity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_07"
down_revision: str | None = "20260808_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_offers",
        sa.Column("affiliate_url_template_key", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_bank_offers_bank_product",
        "bank_offers",
        ["bank_id", "product_name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_bank_offers_bank_product", "bank_offers", type_="unique")
    op.drop_column("bank_offers", "affiliate_url_template_key")
