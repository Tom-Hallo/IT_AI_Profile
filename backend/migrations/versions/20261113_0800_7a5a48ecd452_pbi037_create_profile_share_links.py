"""pbi037_create_profile_share_links

Revision ID: 7a5a48ecd452
Revises: pbi024_roadmap_tracking
Create Date: 2026-11-13 08:00:48.677846
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7a5a48ecd452"
down_revision: str | Sequence[str] | None = "pbi024_roadmap_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profile_share_links",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "allowed_fields",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="ita",
    )

    op.create_index(
        "ix_ita_profile_share_links_user_id",
        "profile_share_links",
        ["user_id"],
        schema="ita",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ita_profile_share_links_user_id",
        table_name="profile_share_links",
        schema="ita",
    )
    op.drop_table("profile_share_links", schema="ita")
