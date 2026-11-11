"""PBI-016 rubric and score tables.

Revision ID: pbi016rubric01
Revises: b6d41a8c9e20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "pbi016rubric01"
down_revision = "b6d41a8c9e20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rubric_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("criteria", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("kind", "version"),
        schema="ita",
    )
    op.create_table(
        "skill_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("ita.users.id"), nullable=False
        ),
        sa.Column(
            "repository_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.repositories.id"),
            nullable=False,
        ),
        sa.Column(
            "report_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.analysis_reports.id"),
            nullable=False,
        ),
        sa.Column(
            "rubric_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.rubric_versions.id"),
            nullable=False,
        ),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("technology", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("score", sa.Integer()),
        sa.Column("breakdown", postgresql.JSONB(), nullable=False),
        sa.Column("explanation", sa.String(500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score BETWEEN 0 AND 100)", name="ck_skill_score_range"
        ),
        schema="ita",
    )
    op.create_index(
        "ix_skill_scores_user_id", "skill_scores", ["user_id"], schema="ita"
    )
    op.create_table(
        "score_evidence_links",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "score_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.skill_scores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.analysis_evidence.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("score_id", "evidence_id"),
        schema="ita",
    )


def downgrade():
    op.drop_table("score_evidence_links", schema="ita")
    op.drop_index("ix_skill_scores_user_id", table_name="skill_scores", schema="ita")
    op.drop_table("skill_scores", schema="ita")
    op.drop_table("rubric_versions", schema="ita")
