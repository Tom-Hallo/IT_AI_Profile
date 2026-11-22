"""Add update_roadmap to ai_event_tool check constraint."""

from alembic import op

revision = "add_update_roadmap_tool"
down_revision = "join_roadmap_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ita.ai_usage_events
        DROP CONSTRAINT IF EXISTS ck_ai_usage_events_ai_event_tool;
    """)
    op.execute("""
        ALTER TABLE ita.ai_usage_events
        ADD CONSTRAINT ck_ai_usage_events_ai_event_tool
        CHECK (((tool)::text = ANY ((ARRAY[
            'create_cv'::character varying,
            'create_roadmap'::character varying,
            'update_roadmap'::character varying,
            'reanalyze_repository'::character varying
        ])::text[])));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE ita.ai_usage_events
        DROP CONSTRAINT IF EXISTS ck_ai_usage_events_ai_event_tool;
    """)
    op.execute("""
        ALTER TABLE ita.ai_usage_events
        ADD CONSTRAINT ck_ai_usage_events_ai_event_tool
        CHECK (((tool)::text = ANY ((ARRAY[
            'create_cv'::character varying,
            'create_roadmap'::character varying,
            'reanalyze_repository'::character varying
        ])::text[])));
    """)
