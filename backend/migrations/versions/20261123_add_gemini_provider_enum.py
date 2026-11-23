"""Add gemini to mentor_audit_provider and ai_event_provider check constraints."""

from alembic import op

revision = "add_gemini_provider"
down_revision = "add_update_roadmap_tool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ita.mentor_actions
        DROP CONSTRAINT IF EXISTS ck_mentor_actions_mentor_audit_provider;
    """)
    op.execute("""
        ALTER TABLE ita.mentor_actions
        ADD CONSTRAINT ck_mentor_actions_mentor_audit_provider
        CHECK (audit_provider IS NULL OR (audit_provider)::text = ANY (ARRAY[
            'openai'::text,
            'ollama'::text,
            'gemini'::text
        ]));
    """)

    op.execute("""
        ALTER TABLE ita.ai_usage_events
        DROP CONSTRAINT IF EXISTS ck_ai_usage_events_ai_event_provider;
    """)
    op.execute("""
        ALTER TABLE ita.ai_usage_events
        ADD CONSTRAINT ck_ai_usage_events_ai_event_provider
        CHECK (provider IS NULL OR (provider)::text = ANY (ARRAY[
            'openai'::text,
            'ollama'::text,
            'gemini'::text
        ]));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE ita.mentor_actions
        DROP CONSTRAINT IF EXISTS ck_mentor_actions_mentor_audit_provider;
    """)
    op.execute("""
        ALTER TABLE ita.mentor_actions
        ADD CONSTRAINT ck_mentor_actions_mentor_audit_provider
        CHECK (audit_provider IS NULL OR (audit_provider)::text = ANY (ARRAY[
            'openai'::text,
            'ollama'::text
        ]));
    """)

    op.execute("""
        ALTER TABLE ita.ai_usage_events
        DROP CONSTRAINT IF EXISTS ck_ai_usage_events_ai_event_provider;
    """)
    op.execute("""
        ALTER TABLE ita.ai_usage_events
        ADD CONSTRAINT ck_ai_usage_events_ai_event_provider
        CHECK (provider IS NULL OR (provider)::text = ANY (ARRAY[
            'openai'::text,
            'ollama'::text
        ]));
    """)
