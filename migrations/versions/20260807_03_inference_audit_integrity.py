"""Enforce model and prediction integrity in the inference audit log."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260807_03"
down_revision: str | None = "20260806_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "scoring_requests",
        "model_version",
        existing_type=sa.String(length=128),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_scoring_requests_model_version",
        "scoring_requests",
        "model_registry",
        ["model_version"],
        ["model_version"],
    )
    op.create_index(
        "ix_scoring_requests_model_version_received_at",
        "scoring_requests",
        ["model_version", "received_at"],
    )

    op.alter_column(
        "scoring_predictions",
        "default_probability",
        existing_type=sa.Float(),
        nullable=False,
    )
    op.alter_column(
        "scoring_predictions",
        "risk_band",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.alter_column(
        "scoring_predictions",
        "top_reason_codes",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_scoring_predictions_probability_range",
        "scoring_predictions",
        "default_probability >= 0 AND default_probability <= 1",
    )
    op.create_check_constraint(
        "ck_scoring_predictions_risk_band_nonempty",
        "scoring_predictions",
        "char_length(risk_band) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_scoring_predictions_risk_band_nonempty",
        "scoring_predictions",
        type_="check",
    )
    op.drop_constraint(
        "ck_scoring_predictions_probability_range",
        "scoring_predictions",
        type_="check",
    )
    op.alter_column(
        "scoring_predictions",
        "top_reason_codes",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )
    op.alter_column(
        "scoring_predictions",
        "risk_band",
        existing_type=sa.String(length=32),
        nullable=True,
    )
    op.alter_column(
        "scoring_predictions",
        "default_probability",
        existing_type=sa.Float(),
        nullable=True,
    )

    op.drop_index(
        "ix_scoring_requests_model_version_received_at",
        table_name="scoring_requests",
    )
    op.drop_constraint(
        "fk_scoring_requests_model_version",
        "scoring_requests",
        type_="foreignkey",
    )
    op.alter_column(
        "scoring_requests",
        "model_version",
        existing_type=sa.String(length=128),
        nullable=True,
    )
