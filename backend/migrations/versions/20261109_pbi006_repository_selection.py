"""PBI-006 repository analysis selections."""

import sqlalchemy as sa
from alembic import op

revision = "pbi006_selection"
down_revision = "886985c725a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repository_selection_settings",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "scope IN ('public', 'private', 'combined')",
            name="ck_repository_selection_settings_valid_scope",
        ),
        schema="ita",
    )
    op.create_table(
        "repository_selections",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("github_repository_id", sa.BigInteger(), primary_key=True),
        schema="ita",
    )


def downgrade() -> None:
    op.drop_table("repository_selections", schema="ita")
    op.drop_table("repository_selection_settings", schema="ita")
