"""PBI-015: link versioned findings to evidence within the same report.

Revision ID: pbi015findings01
Revises: b14f014c014a, pbi016rubric01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "pbi015findings01"
down_revision: str | Sequence[str] | None = ("b14f014c014a", "pbi016rubric01")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_analysis_evidence_id_report",
        "analysis_evidence",
        ["id", "report_id"],
        schema="ita",
    )
    op.create_table(
        "analysis_findings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "report_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.analysis_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("finding_key", sa.String(255), nullable=False),
        sa.Column("finding_type", sa.String(50), nullable=False),
        sa.Column("classification", sa.String(100), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column(
            "analyzer_version",
            sa.String(40),
            nullable=False,
            server_default="pbi012-legacy",
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("report_id", "finding_key", name="uq_finding_report_key"),
        sa.UniqueConstraint("id", "report_id", name="uq_finding_id_report"),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="finding_confidence_range",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published')", name="finding_status_valid"
        ),
        schema="ita",
    )
    op.create_index(
        "ix_ita_analysis_findings_report_id",
        "analysis_findings",
        ["report_id"],
        schema="ita",
    )
    op.create_table(
        "finding_evidence_links",
        sa.Column("finding_id", sa.BigInteger(), primary_key=True),
        sa.Column("evidence_id", sa.BigInteger(), primary_key=True),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_id", "report_id"],
            ["ita.analysis_findings.id", "ita.analysis_findings.report_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "report_id"],
            ["ita.analysis_evidence.id", "ita.analysis_evidence.report_id"],
            ondelete="CASCADE",
        ),
        schema="ita",
    )
    op.create_index(
        "ix_finding_evidence_links_report",
        "finding_evidence_links",
        ["report_id"],
        schema="ita",
    )
    op.create_index(
        "ix_finding_evidence_links_evidence",
        "finding_evidence_links",
        ["evidence_id"],
        schema="ita",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_finding_evidence_links_evidence",
        table_name="finding_evidence_links",
        schema="ita",
    )
    op.drop_index(
        "ix_finding_evidence_links_report",
        table_name="finding_evidence_links",
        schema="ita",
    )
    op.drop_table("finding_evidence_links", schema="ita")
    op.drop_index(
        "ix_ita_analysis_findings_report_id",
        table_name="analysis_findings",
        schema="ita",
    )
    op.drop_table("analysis_findings", schema="ita")
    op.drop_constraint(
        "uq_analysis_evidence_id_report",
        "analysis_evidence",
        type_="unique",
        schema="ita",
    )
