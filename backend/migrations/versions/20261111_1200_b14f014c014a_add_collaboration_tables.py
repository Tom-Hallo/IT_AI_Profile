"""Create collaboration analyses and collaboration evidence tables (PBI-014).

Revision ID: b14f014c014a
Revises: a13f013b013a
Create Date: 2026-11-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b14f014c014a"
down_revision: str | Sequence[str] | None = "a13f013b013a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ita"


def upgrade() -> None:
    op.create_table(
        "collaboration_analyses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "repository_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.repositories.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ita.analysis_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "report_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.analysis_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "total_prs_analyzed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "merged_prs_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "closed_unmerged_prs_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "open_prs_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "user_prs_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "external_prs_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_reviews_analyzed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "approved_reviews_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "changes_requested_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "commented_reviews_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "dismissed_reviews_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "user_reviews_conducted_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "user_reviews_received_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_checks_analyzed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "successful_checks_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "failed_checks_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "pending_checks_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "other_checks_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "problem_solving_sequences_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "coverage_status",
            sa.String(length=50),
            nullable=False,
            server_default="complete",
        ),
        sa.Column(
            "confidence",
            sa.String(length=20),
            nullable=False,
            server_default="high",
        ),
        sa.Column("time_range", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "limitations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "collaboration_observations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "problem_solving_observations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "summary_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_collab_analysis_repo_user",
        "collaboration_analyses",
        ["repository_id", "user_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "collaboration_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "analysis_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.collaboration_analyses.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "repository_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.repositories.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("evidence_type", sa.String(length=50), nullable=False),
        sa.Column("target_identifier", sa.String(length=255), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("commit_sha", sa.String(length=40), nullable=True),
        sa.Column("check_name", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=True),
        sa.Column("conclusion", sa.String(length=50), nullable=True),
        sa.Column("actor_login", sa.String(length=255), nullable=True),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("actor_type", sa.String(length=50), nullable=True),
        sa.Column(
            "is_profile_owner",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("html_url", sa.String(length=512), nullable=True),
        sa.Column("title_or_message", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_collab_ev_analysis_id",
        "collaboration_evidence",
        ["analysis_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_collab_ev_repo_target",
        "collaboration_evidence",
        ["repository_id", "target_identifier"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_collab_ev_pr_number",
        "collaboration_evidence",
        ["pr_number"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_collab_ev_commit_sha",
        "collaboration_evidence",
        ["commit_sha"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collab_ev_commit_sha",
        table_name="collaboration_evidence",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_collab_ev_pr_number",
        table_name="collaboration_evidence",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_collab_ev_repo_target",
        table_name="collaboration_evidence",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_collab_ev_analysis_id",
        table_name="collaboration_evidence",
        schema=SCHEMA,
    )
    op.drop_table("collaboration_evidence", schema=SCHEMA)

    op.drop_index(
        "ix_collab_analysis_repo_user",
        table_name="collaboration_analyses",
        schema=SCHEMA,
    )
    op.drop_table("collaboration_analyses", schema=SCHEMA)
