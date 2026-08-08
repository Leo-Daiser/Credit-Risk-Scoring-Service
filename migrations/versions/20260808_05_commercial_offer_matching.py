"""Add privacy-light offer catalog and commercial event tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260808_05"
down_revision: str | None = "20260807_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "bank_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bank_id", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("product_type", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("min_age_band", sa.String(length=32), nullable=False),
        sa.Column("max_age_band", sa.String(length=32), nullable=False),
        sa.Column("allowed_age_bands", JSON_TYPE, nullable=False),
        sa.Column("allowed_regions", JSON_TYPE, nullable=False),
        sa.Column("allowed_employment_types", JSON_TYPE, nullable=False),
        sa.Column("allowed_credit_history_bands", JSON_TYPE, nullable=False),
        sa.Column("min_amount", sa.Float(), nullable=False),
        sa.Column("max_amount", sa.Float(), nullable=False),
        sa.Column("min_term_months", sa.Integer(), nullable=False),
        sa.Column("max_term_months", sa.Integer(), nullable=False),
        sa.Column("min_income_band", sa.String(length=32), nullable=False),
        sa.Column("max_pti_band", sa.String(length=32), nullable=False),
        sa.Column("risk_band_policy", JSON_TYPE, nullable=False),
        sa.Column("affiliate_url_template", sa.Text(), nullable=False),
        sa.Column("advertiser_name", sa.String(length=255), nullable=False),
        sa.Column("erid", sa.String(length=128), nullable=True),
        sa.Column("ad_label_text", sa.String(length=255), nullable=False),
        sa.Column("legal_disclaimer", sa.Text(), nullable=False),
        sa.Column("commission_type", sa.String(length=32), nullable=False),
        sa.Column("commission_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "min_amount > 0 AND max_amount >= min_amount", name="ck_bank_offers_amount"
        ),
        sa.CheckConstraint(
            "min_term_months >= 3 AND max_term_months >= min_term_months",
            name="ck_bank_offers_term",
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 100", name="ck_bank_offers_priority"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bank_offers_active_priority", "bank_offers", ["is_active", "priority"]
    )
    op.create_table(
        "anonymous_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("utm_source", sa.String(length=128), nullable=True),
        sa.Column("utm_medium", sa.String(length=128), nullable=True),
        sa.Column("utm_campaign", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_key_hash"),
    )
    op.create_table(
        "credit_profile_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("anonymous_session_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("risk_band", sa.String(length=32), nullable=False),
        sa.Column("pti_band", sa.String(length=32), nullable=False),
        sa.Column("affordability_band", sa.String(length=32), nullable=False),
        sa.Column("age_band", sa.String(length=32), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("income_band", sa.String(length=32), nullable=False),
        sa.Column("requested_amount_band", sa.String(length=32), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("employment_type", sa.String(length=32), nullable=False),
        sa.Column("credit_history_band", sa.String(length=32), nullable=False),
        sa.Column("loan_purpose", sa.String(length=32), nullable=False),
        sa.Column("data_coverage", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["anonymous_session_id"], ["anonymous_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id"),
    )
    op.create_index(
        "ix_credit_profile_events_profile_id", "credit_profile_events", ["profile_id"]
    )
    op.create_index(
        "ix_credit_profile_events_created_at", "credit_profile_events", ["created_at"]
    )
    op.create_table(
        "offer_impressions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("anonymous_session_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("score_breakdown_json", JSON_TYPE, nullable=False),
        sa.Column("shown_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["anonymous_session_id"], ["anonymous_sessions.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["bank_offers.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["credit_profile_events.profile_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_offer_impressions_offer_shown", "offer_impressions", ["offer_id", "shown_at"]
    )
    op.create_index(
        "ix_offer_impressions_profile_id", "offer_impressions", ["profile_id"]
    )
    op.create_table(
        "offer_clicks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("click_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("anonymous_session_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("clicked_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("redirect_url_hash", sa.String(length=64), nullable=False),
        sa.Column("utm_source", sa.String(length=128), nullable=True),
        sa.Column("utm_medium", sa.String(length=128), nullable=True),
        sa.Column("utm_campaign", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["anonymous_session_id"], ["anonymous_sessions.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["bank_offers.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["credit_profile_events.profile_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("click_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_offer_clicks_offer_clicked", "offer_clicks", ["offer_id", "clicked_at"]
    )
    op.create_index("ix_offer_clicks_profile_id", "offer_clicks", ["profile_id"])
    op.create_table(
        "partner_postbacks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("postback_id", sa.String(length=128), nullable=False),
        sa.Column("click_id", sa.String(length=36), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approved_amount_band", sa.String(length=32), nullable=True),
        sa.Column("issued_amount_band", sa.String(length=32), nullable=True),
        sa.Column("commission_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("received_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("raw_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["click_id"], ["offer_clicks.click_id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["bank_offers.id"]),
        sa.CheckConstraint(
            "status IN ('application_started', 'application_submitted', 'approved', "
            "'rejected', 'issued', 'cancelled')",
            name="ck_partner_postbacks_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("click_id", "status", name="uq_partner_postback_click_status"),
        sa.UniqueConstraint("postback_id"),
    )
    op.create_index(
        "ix_partner_postbacks_offer_status", "partner_postbacks", ["offer_id", "status"]
    )
    op.create_index(
        "ix_partner_postbacks_received_at", "partner_postbacks", ["received_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_partner_postbacks_received_at", table_name="partner_postbacks")
    op.drop_index("ix_partner_postbacks_offer_status", table_name="partner_postbacks")
    op.drop_table("partner_postbacks")
    op.drop_index("ix_offer_clicks_profile_id", table_name="offer_clicks")
    op.drop_index("ix_offer_clicks_offer_clicked", table_name="offer_clicks")
    op.drop_table("offer_clicks")
    op.drop_index("ix_offer_impressions_profile_id", table_name="offer_impressions")
    op.drop_index("ix_offer_impressions_offer_shown", table_name="offer_impressions")
    op.drop_table("offer_impressions")
    op.drop_index("ix_credit_profile_events_created_at", table_name="credit_profile_events")
    op.drop_index("ix_credit_profile_events_profile_id", table_name="credit_profile_events")
    op.drop_table("credit_profile_events")
    op.drop_table("anonymous_sessions")
    op.drop_index("ix_bank_offers_active_priority", table_name="bank_offers")
    op.drop_table("bank_offers")
