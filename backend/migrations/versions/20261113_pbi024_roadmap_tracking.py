"""PBI-024 roadmap tracking. RENAME and set down_revision to your actual Alembic HEAD.

Revision ID: pbi024_roadmap_tracking
Revises: pbi030_snapshots
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "pbi024_roadmap_tracking"
down_revision = "pbi030_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "roadmap_milestones",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "roadmap_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.roadmaps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_key", sa.String(128), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("required_skills", JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("roadmap_id", "external_key", name="uq_rm_milestone_key"),
        schema="ita",
    )
    op.create_index(
        "ix_roadmap_milestones_roadmap_id",
        "roadmap_milestones",
        ["roadmap_id"],
        schema="ita",
    )
    op.create_table(
        "roadmap_milestone_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "milestone_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.roadmap_milestones.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.users.id"),
            nullable=False,
        ),
        sa.Column("old_status", sa.String(24)),
        sa.Column("new_status", sa.String(24), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="ita",
    )
    op.create_index(
        "ix_roadmap_milestone_history_milestone_id",
        "roadmap_milestone_history",
        ["milestone_id"],
        schema="ita",
    )
    op.create_table(
        "roadmap_suggestions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "roadmap_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.roadmaps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "milestone_id",
            sa.BigInteger(),
            sa.ForeignKey("ita.roadmap_milestones.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_key", sa.String(128), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "roadmap_id",
            "snapshot_key",
            "milestone_id",
            "action",
            name="uq_rm_suggestion_idempotent",
        ),
        schema="ita",
    )
    op.create_index(
        "ix_roadmap_suggestions_roadmap_id",
        "roadmap_suggestions",
        ["roadmap_id"],
        schema="ita",
    )


def downgrade():
    op.drop_index(
        "ix_roadmap_suggestions_roadmap_id",
        table_name="roadmap_suggestions",
        schema="ita",
    )
    op.drop_table("roadmap_suggestions", schema="ita")
    op.drop_index(
        "ix_roadmap_milestone_history_milestone_id",
        table_name="roadmap_milestone_history",
        schema="ita",
    )
    op.drop_table("roadmap_milestone_history", schema="ita")
    op.drop_index(
        "ix_roadmap_milestones_roadmap_id",
        table_name="roadmap_milestones",
        schema="ita",
    )
    op.drop_table("roadmap_milestones", schema="ita")
