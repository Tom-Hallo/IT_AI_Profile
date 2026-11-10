"""add analysis jobs

Revision ID: 886985c725a6
Revises: pbi009_github_sync
Create Date: 2026-11-09 07:59:01.916428

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "886985c725a6"
down_revision: str | Sequence[str] | None = "pbi009_github_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.users.id"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.repositories.id"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "progress",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "step",
            sa.String(length=80),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "retry_of",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ita.analysis_jobs.id"),
            nullable=True,
        ),
        sa.Column("execution_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100", name="analysis_progress_range"
        ),
        schema="ita",
    )
    op.create_index(
        "uq_analysis_active_resource",
        "analysis_jobs",
        ["user_id", "repo_id", "scope"],
        unique=True,
        schema="ita",
        postgresql_where=sa.text("status IN ('queued','running','cancel_requested')"),
    )
    op.create_table(
        "analysis_job_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ita.analysis_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("step", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="ita",
    )
    op.create_index(
        "ix_ita_analysis_job_events_job_id",
        "analysis_job_events",
        ["job_id"],
        schema="ita",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_ita_analysis_job_events_job_id",
        table_name="analysis_job_events",
        schema="ita",
    )
    op.drop_table("analysis_job_events", schema="ita")
    op.drop_index(
        "uq_analysis_active_resource",
        table_name="analysis_jobs",
        schema="ita",
    )
    op.drop_table("analysis_jobs", schema="ita")
