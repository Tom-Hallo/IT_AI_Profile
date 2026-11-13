"""Persist mentor action confirmations and their audit trail."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "pbi022_mentor_actions"
down_revision = "pbi020_scoring_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mentor_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("tool", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("result_id", sa.String(36), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["ita.users.id"], ondelete="CASCADE"),
        schema="ita",
    )
    op.create_index(
        "ix_mentor_actions_user_id", "mentor_actions", ["user_id"], schema="ita"
    )
    op.create_index(
        "ix_mentor_actions_status_expires_at",
        "mentor_actions",
        ["status", "expires_at"],
        schema="ita",
    )
    op.create_table(
        "mentor_action_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["action_id"], ["ita.mentor_actions.id"], ondelete="CASCADE"
        ),
        schema="ita",
    )
    op.create_index(
        "ix_mentor_action_events_action_id",
        "mentor_action_events",
        ["action_id"],
        schema="ita",
    )


def downgrade() -> None:
    op.drop_table("mentor_action_events", schema="ita")
    op.drop_table("mentor_actions", schema="ita")
