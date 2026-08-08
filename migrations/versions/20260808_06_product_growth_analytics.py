"""Add product-growth analytics and experiment dimensions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_06"
down_revision: str | None = "20260808_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_offers",
        sa.Column("partner_id", sa.String(length=64), server_default="demo", nullable=False),
    )
    op.add_column("bank_offers", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column(
        "offer_impressions",
        sa.Column(
            "experiment_variant",
            sa.String(length=64),
            server_default="rules_v1",
            nullable=False,
        ),
    )
    op.add_column(
        "offer_clicks",
        sa.Column(
            "experiment_variant",
            sa.String(length=64),
            server_default="rules_v1",
            nullable=False,
        ),
    )
    op.create_table(
        "commercial_funnel_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("anonymous_session_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.String(length=36), nullable=True),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("click_id", sa.String(length=36), nullable=True),
        sa.Column("risk_band", sa.String(length=32), nullable=True),
        sa.Column("pti_band", sa.String(length=32), nullable=True),
        sa.Column(
            "experiment_variant",
            sa.String(length=64),
            server_default="rules_v1",
            nullable=False,
        ),
        sa.Column("event_value", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["anonymous_session_id"], ["anonymous_sessions.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["bank_offers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_commercial_funnel_events_type_created",
        "commercial_funnel_events",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_commercial_funnel_events_profile",
        "commercial_funnel_events",
        ["profile_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_commercial_funnel_events_profile",
        table_name="commercial_funnel_events",
    )
    op.drop_index(
        "ix_commercial_funnel_events_type_created",
        table_name="commercial_funnel_events",
    )
    op.drop_table("commercial_funnel_events")
    op.drop_column("offer_clicks", "experiment_variant")
    op.drop_column("offer_impressions", "experiment_variant")
    op.drop_column("bank_offers", "expires_at")
    op.drop_column("bank_offers", "partner_id")
