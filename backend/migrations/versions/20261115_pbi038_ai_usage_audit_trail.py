"""Create owner-scoped AI usage audit and retain provider on new tool proposals."""

import sqlalchemy as sa
from alembic import op

revision = "pbi038_ai_usage_audit_trail"
down_revision = "pbi029_cv_studio_versions"
branch_labels = None
depends_on = None


def choices(*values: str, name: str) -> sa.Enum:
    return sa.Enum(
        *values, name=name, native_enum=False, length=24, create_constraint=True
    )


def upgrade() -> None:
    op.add_column(
        "mentor_actions",
        sa.Column(
            "audit_provider",
            choices("openai", "ollama", name="mentor_audit_provider"),
            nullable=True,
        ),
        schema="ita",
    )
    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "feature",
            choices("mentor", "cv_studio", "repository_ai", name="ai_event_feature"),
            nullable=False,
        ),
        sa.Column(
            "phase",
            choices("context", "provider", "tool", name="ai_event_phase"),
            nullable=False,
        ),
        sa.Column(
            "source",
            choices(
                "github",
                "github_public",
                "github_private",
                "cv",
                "jd",
                "roadmap",
                "chat",
                name="ai_event_source",
            ),
            nullable=False,
        ),
        sa.Column("provider", choices("openai", "ollama", name="ai_event_provider")),
        sa.Column(
            "consent",
            choices(
                "selected",
                "double_granted",
                "policy_allowed",
                "denied",
                "confirmed",
                "declined",
                "not_requested",
                name="ai_event_consent",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            choices(
                "retrieved",
                "unavailable",
                "started",
                "succeeded",
                "denied",
                "failed",
                "timeout",
                "cancelled",
                "skipped",
                "proposed",
                "confirmed",
                "declined",
                "expired",
                "queue_deferred",
                name="ai_event_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "tool",
            choices(
                "create_cv",
                "create_roadmap",
                "reanalyze_repository",
                name="ai_event_tool",
            ),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["ita.users.id"], ondelete="CASCADE"),
        schema="ita",
    )
    op.create_index(
        "ix_ai_usage_events_owner_id",
        "ai_usage_events",
        ["user_id", "id"],
        schema="ita",
    )


def downgrade() -> None:
    op.drop_table("ai_usage_events", schema="ita")
    op.drop_column("mentor_actions", "audit_provider", schema="ita")
