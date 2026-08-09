"""Add public offer presentation and compliance fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_08"
down_revision: str | None = "20260808_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bank_offers", sa.Column("full_cost_range_text", sa.Text(), nullable=True))
    op.add_column(
        "bank_offers",
        sa.Column(
            "compensation_disclosure",
            sa.Text(),
            nullable=False,
            server_default="Сервис может получить вознаграждение за переход.",
        ),
    )
    op.add_column("bank_offers", sa.Column("partner_terms_url", sa.Text(), nullable=True))
    op.add_column("bank_offers", sa.Column("main_benefit", sa.String(length=255), nullable=True))
    op.add_column(
        "bank_offers",
        sa.Column("display_warnings", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "bank_offers",
        sa.Column(
            "cta_text",
            sa.String(length=64),
            nullable=False,
            server_default="Посмотреть условия",
        ),
    )


def downgrade() -> None:
    op.drop_column("bank_offers", "cta_text")
    op.drop_column("bank_offers", "display_warnings")
    op.drop_column("bank_offers", "main_benefit")
    op.drop_column("bank_offers", "partner_terms_url")
    op.drop_column("bank_offers", "compensation_disclosure")
    op.drop_column("bank_offers", "full_cost_range_text")
