"""Add one-to-one prediction/request constraint to the legacy schema."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260806_02"
down_revision: str | None = "20260806_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_scoring_predictions_request_id",
        "scoring_predictions",
        ["request_id"],
    )
    op.create_foreign_key(
        "fk_scoring_predictions_request_id",
        "scoring_predictions",
        "scoring_requests",
        ["request_id"],
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_scoring_predictions_request_id",
        "scoring_predictions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_scoring_predictions_request_id",
        "scoring_predictions",
        type_="unique",
    )
