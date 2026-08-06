"""Create model registry, inference log and feature statistics tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260806_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_version", sa.String(128), nullable=False, unique=True),
        sa.Column("model_type", sa.String(64), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "scoring_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False, unique=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=True),
        sa.Column("received_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "scoring_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("default_probability", sa.Float(), nullable=True),
        sa.Column("risk_band", sa.String(32), nullable=True),
        sa.Column("top_reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "feature_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature_name", sa.String(256), nullable=False),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("train_mean", sa.Float(), nullable=True),
        sa.Column("train_std", sa.Float(), nullable=True),
        sa.Column("missing_rate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feature_stats")
    op.drop_table("scoring_predictions")
    op.drop_table("scoring_requests")
    op.drop_table("model_registry")
