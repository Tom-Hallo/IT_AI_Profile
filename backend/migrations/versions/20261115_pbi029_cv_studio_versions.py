"""Store editable CV Studio drafts as immutable numbered versions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "pbi029_cv_studio_versions"
down_revision = "560ffcca5e7c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cv_studio_versions",
        sa.Column("document_id", sa.Uuid(), primary_key=True),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("template", sa.String(20), nullable=False),
        sa.Column("lines", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["ita.users.id"], ondelete="CASCADE"),
        schema="ita",
    )
    op.create_index(
        "ix_cv_studio_versions_user_id", "cv_studio_versions", ["user_id"], schema="ita"
    )


def downgrade() -> None:
    op.drop_table("cv_studio_versions", schema="ita")
