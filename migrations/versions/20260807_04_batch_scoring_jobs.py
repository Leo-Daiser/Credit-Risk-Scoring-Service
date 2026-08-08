"""Add durable batch jobs and immutable decision audit fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260807_04"
down_revision: str | None = "20260807_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scoring_predictions",
        sa.Column("decision", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "scoring_predictions",
        sa.Column("decision_threshold", sa.Float(), nullable=True),
    )

    op.create_table(
        "batch_scoring_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("input_format", sa.String(length=16), nullable=False),
        sa.Column("id_column", sa.String(length=128), nullable=False),
        sa.Column("input_path", sa.Text(), nullable=False),
        sa.Column("output_path", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=True),
        sa.Column("rows_processed", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column(
            "summary_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_batch_scoring_jobs_status",
        ),
        sa.CheckConstraint(
            "rows_total IS NULL OR rows_total >= 0",
            name="ck_batch_scoring_jobs_rows_total_nonnegative",
        ),
        sa.CheckConstraint(
            "rows_processed >= 0",
            name="ck_batch_scoring_jobs_rows_processed_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index(
        "ix_batch_scoring_jobs_status_created_at",
        "batch_scoring_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_batch_scoring_jobs_status_created_at",
        table_name="batch_scoring_jobs",
    )
    op.drop_table("batch_scoring_jobs")
    op.drop_column("scoring_predictions", "decision_threshold")
    op.drop_column("scoring_predictions", "decision")
