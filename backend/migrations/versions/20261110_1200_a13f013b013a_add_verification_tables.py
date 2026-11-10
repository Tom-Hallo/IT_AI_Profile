"""Create repository verification and evidence tables (PBI-013).

Revision ID: a13f013b013a
Revises: b6d41a8c9e20
Create Date: 2026-11-10 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a13f013b013a"
down_revision: str | Sequence[str] | None = "b6d41a8c9e20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ita"


def upgrade() -> None:
    op.create_table(
        "repository_verifications",
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
            "provenance_type",
            sa.String(length=50),
            nullable=False,
            server_default="original",
        ),
        sa.Column(
            "ownership_status",
            sa.String(length=50),
            nullable=False,
            server_default="owner",
        ),
        sa.Column(
            "is_fork",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("parent_repo_name", sa.String(length=255), nullable=True),
        sa.Column("parent_repo_url", sa.String(length=512), nullable=True),
        sa.Column(
            "parent_metadata_status",
            sa.String(length=50),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "verification_status",
            sa.String(length=50),
            nullable=False,
            server_default="unknown",
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
        sa.Column(
            "verified_commits_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "unverified_commits_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "verified_prs_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "unverified_prs_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "verified_additions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "verified_deletions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("time_range", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "limitations",
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
            "verified_at",
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
        "ix_repo_verif_repo_user",
        "repository_verifications",
        ["repository_id", "user_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "verification_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "verification_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.repository_verifications.id", ondelete="CASCADE"),
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
        sa.Column("verification_status", sa.String(length=50), nullable=False),
        sa.Column("actor_login", sa.String(length=255), nullable=True),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("actor_type", sa.String(length=50), nullable=True),
        sa.Column("html_url", sa.String(length=512), nullable=True),
        sa.Column("title_or_message", sa.Text(), nullable=True),
        sa.Column(
            "is_merge",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_bot",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_fork_inherited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("additions", sa.Integer(), nullable=True),
        sa.Column("deletions", sa.Integer(), nullable=True),
        sa.Column("pr_state", sa.String(length=50), nullable=True),
        sa.Column("pr_merged", sa.Boolean(), nullable=True),
        sa.Column("source_repo", sa.String(length=255), nullable=True),
        sa.Column("target_repo", sa.String(length=255), nullable=True),
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
        "ix_verif_ev_verif_id",
        "verification_evidence",
        ["verification_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_verif_ev_target",
        "verification_evidence",
        ["repository_id", "target_identifier"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verif_ev_target",
        table_name="verification_evidence",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_verif_ev_verif_id",
        table_name="verification_evidence",
        schema=SCHEMA,
    )
    op.drop_table("verification_evidence", schema=SCHEMA)

    op.drop_index(
        "ix_repo_verif_repo_user",
        table_name="repository_verifications",
        schema=SCHEMA,
    )
    op.drop_table("repository_verifications", schema=SCHEMA)

