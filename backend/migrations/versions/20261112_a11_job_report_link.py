"""Associate successful jobs with their exact analysis report."""

import sqlalchemy as sa
from alembic import op

revision = "a11jobreport01"
down_revision = "a11joboptions01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs", sa.Column("report_id", sa.BigInteger()), schema="ita"
    )
    op.create_foreign_key(
        "fk_analysis_jobs_report_id",
        "analysis_jobs",
        "analysis_reports",
        ["report_id"],
        ["id"],
        source_schema="ita",
        referent_schema="ita",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_analysis_jobs_report_id", "analysis_jobs", schema="ita", type_="foreignkey"
    )
    op.drop_column("analysis_jobs", "report_id", schema="ita")
