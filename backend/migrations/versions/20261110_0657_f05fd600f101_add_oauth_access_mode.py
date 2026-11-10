"""add_oauth_access_mode

Revision ID: f05fd600f101
Revises: 9544e44d3951
Create Date: 2026-11-10 06:57:47.159884
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f05fd600f101"
down_revision: str | Sequence[str] | None = "9544e44d3951"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_oauth_accounts",
        sa.Column(
            "access_mode",
            sa.String(length=20),
            server_default="public_only",
            nullable=False,
        ),
        schema="ita",
    )


def downgrade() -> None:
    op.drop_column("user_oauth_accounts", "access_mode", schema="ita")
