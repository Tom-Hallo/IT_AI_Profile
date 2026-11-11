"""Persist branch and time filters for analysis jobs."""

import sqlalchemy as sa
from alembic import op

revision = "a11joboptions01"
down_revision = "pbi015findings01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs", sa.Column("request_options", sa.JSON()), schema="ita"
    )


def downgrade() -> None:
    op.drop_column("analysis_jobs", "request_options", schema="ita")
