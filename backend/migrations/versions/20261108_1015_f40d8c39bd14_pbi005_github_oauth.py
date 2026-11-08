"""pbi005_github_oauth

Revision ID: f40d8c39bd14
Revises: pbi002_initial_schema
Create Date: 2026-11-08 10:15:49.144328

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f40d8c39bd14"
down_revision: str | Sequence[str] | None = "pbi002_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create OAuth account table and allow OAuth-only users."""

    # OAuth-only users do not need an internal password.
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
        schema="ita",
    )

    # Store external OAuth identities linked to application users.
    op.create_table(
        "user_oauth_accounts",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "provider_user_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["ita.users.id"],
            name="fk_user_oauth_accounts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_user_oauth_accounts",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_user_oauth_accounts_provider_provider_user_id",
        ),
        schema="ita",
        comment="External OAuth identities linked to users",
    )

    op.create_index(
        "ix_user_oauth_accounts_user_id",
        "user_oauth_accounts",
        ["user_id"],
        unique=False,
        schema="ita",
    )


def downgrade() -> None:
    """Remove OAuth account table and restore password requirement."""

    op.drop_index(
        "ix_user_oauth_accounts_user_id",
        table_name="user_oauth_accounts",
        schema="ita",
    )

    op.drop_table(
        "user_oauth_accounts",
        schema="ita",
    )

    # This will fail if OAuth-only users still have NULL passwords.
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
        schema="ita",
    )
