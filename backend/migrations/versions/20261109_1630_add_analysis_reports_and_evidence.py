"""add analysis reports and evidence

Revision ID: 9c8b7a6d5e4f
Revises: 886985c725a6
Create Date: 2026-11-09 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9c8b7a6d5e4f"
down_revision: str | Sequence[str] | None = "886985c725a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ita"


def upgrade() -> None:
    """Create persistent analysis_reports and analysis_evidence tables."""
    op.create_table(
        "analysis_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "repository_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.repositories.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("commit_sha", sa.String(length=40), nullable=False, index=True),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(length=40), nullable=False, server_default="all"),
        sa.Column("time_range", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("structure", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("languages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "frameworks", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "architecture", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("budget", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_analysis_reports_repo_commit",
        "analysis_reports",
        ["repository_id", "commit_sha"],
        schema=SCHEMA,
    )

    op.create_table(
        "analysis_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "report_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.analysis_reports.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "repository_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.repositories.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("commit_sha", sa.String(length=40), nullable=False, index=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("finding_type", sa.String(length=50), nullable=False),
        sa.Column("classification", sa.String(length=100), nullable=False),
        sa.Column("evidence_source", sa.String(length=50), nullable=False),
        sa.Column("detection_method", sa.String(length=50), nullable=False),
        sa.Column(
            "confidence", sa.String(length=20), nullable=False, server_default="high"
        ),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("matched_content", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(length=40), nullable=False, server_default="all"),
        sa.Column("time_range", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_analysis_evidence_repo_commit",
        "analysis_evidence",
        ["repository_id", "commit_sha"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Drop analysis_evidence and analysis_reports tables."""
    op.drop_index(
        "ix_analysis_evidence_repo_commit",
        table_name="analysis_evidence",
        schema=SCHEMA,
    )
    op.drop_table("analysis_evidence", schema=SCHEMA)
    op.drop_index(
        "ix_analysis_reports_repo_commit",
        table_name="analysis_reports",
        schema=SCHEMA,
    )
    op.drop_table("analysis_reports", schema=SCHEMA)
