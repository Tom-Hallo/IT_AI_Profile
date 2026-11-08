"""pbi009_github_sync

Revision ID: pbi009_github_sync
Revises: f40d8c39bd14
Create Date: 2026-11-08 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "pbi009_github_sync"
down_revision: str | Sequence[str] | None = "f40d8c39bd14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ita"


def upgrade() -> None:
    """Add encrypted OAuth token fields and repository sync metadata."""

    # 1. Update user_oauth_accounts with encrypted access token and scope
    op.add_column(
        "user_oauth_accounts",
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "user_oauth_accounts",
        sa.Column("scope", sa.String(length=255), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "user_oauth_accounts",
        sa.Column("token_updated_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    # 2. Update repositories with metadata for PBI-009
    op.add_column(
        "repositories",
        sa.Column("full_name", sa.String(length=255), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column(
            "default_branch",
            sa.String(length=100),
            server_default="main",
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column(
            "is_fork",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column("fork_source", sa.String(length=255), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column("languages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column("primary_language", sa.String(length=100), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column(
            "stars_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column(
            "forks_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column(
            "open_issues_count",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column(
            "size_kb",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column(
            "archived",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column(
            "disabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column("github_created_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column("github_updated_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "repositories",
        sa.Column(
            "sync_status",
            sa.String(length=50),
            server_default="synced",
            nullable=False,
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Drop added columns from repositories and user_oauth_accounts."""

    # 1. Drop columns from repositories
    op.drop_column("repositories", "sync_status", schema=SCHEMA)
    op.drop_column("repositories", "last_synced_at", schema=SCHEMA)
    op.drop_column("repositories", "github_updated_at", schema=SCHEMA)
    op.drop_column("repositories", "github_created_at", schema=SCHEMA)
    op.drop_column("repositories", "pushed_at", schema=SCHEMA)
    op.drop_column("repositories", "disabled", schema=SCHEMA)
    op.drop_column("repositories", "archived", schema=SCHEMA)
    op.drop_column("repositories", "size_kb", schema=SCHEMA)
    op.drop_column("repositories", "open_issues_count", schema=SCHEMA)
    op.drop_column("repositories", "forks_count", schema=SCHEMA)
    op.drop_column("repositories", "stars_count", schema=SCHEMA)
    op.drop_column("repositories", "primary_language", schema=SCHEMA)
    op.drop_column("repositories", "languages", schema=SCHEMA)
    op.drop_column("repositories", "fork_source", schema=SCHEMA)
    op.drop_column("repositories", "is_fork", schema=SCHEMA)
    op.drop_column("repositories", "default_branch", schema=SCHEMA)
    op.drop_column("repositories", "full_name", schema=SCHEMA)

    # 2. Drop columns from user_oauth_accounts
    op.drop_column("user_oauth_accounts", "token_updated_at", schema=SCHEMA)
    op.drop_column("user_oauth_accounts", "scope", schema=SCHEMA)
    op.drop_column("user_oauth_accounts", "encrypted_access_token", schema=SCHEMA)
