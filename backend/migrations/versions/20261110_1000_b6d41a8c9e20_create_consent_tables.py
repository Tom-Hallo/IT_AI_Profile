"""Create missing consent and cleanup tables.

Revision ID: b6d41a8c9e20
Revises: f05fd600f101
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b6d41a8c9e20"
down_revision: str | Sequence[str] | None = "f05fd600f101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ita"


def upgrade() -> None:
    op.create_table(
        "private_consents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consent_type", sa.String(32), nullable=False),
        sa.Column("provider_key", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.String(30), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id",
            "repository_id",
            "consent_type",
            "provider_key",
            name="uq_private_consent_identity",
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_private_consents_user_id",
        "private_consents",
        ["user_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_private_consents_repository_id",
        "private_consents",
        ["repository_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "private_consent_audits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("consent_type", sa.String(32), nullable=False),
        sa.Column("provider_key", sa.String(80), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("policy_version", sa.String(30), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_private_consent_audits_user_id",
        "private_consent_audits",
        ["user_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "cleanup_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ita.analysis_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(24), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", name="uq_cleanup_job"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("cleanup_requests", schema=SCHEMA)

    op.drop_index(
        "ix_private_consent_audits_user_id",
        table_name="private_consent_audits",
        schema=SCHEMA,
    )
    op.drop_table("private_consent_audits", schema=SCHEMA)

    op.drop_index(
        "ix_private_consents_repository_id",
        table_name="private_consents",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_private_consents_user_id",
        table_name="private_consents",
        schema=SCHEMA,
    )
    op.drop_table("private_consents", schema=SCHEMA)
