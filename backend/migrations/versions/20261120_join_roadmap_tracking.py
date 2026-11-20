"""Connect existing generated career roadmaps to progress tracking."""

from alembic import op

revision = "join_roadmap_tracking"
down_revision = "pbi038_ai_usage_audit_trail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE ita.roadmaps
        SET data = data || jsonb_build_object(
            'analysis_context',
            jsonb_build_object(
                'scope', 'public', 'rubric', '2.1.0', 'period', 'all_time'
            )
        )
        WHERE data->>'version' = 'pbi023-v1' AND NOT data ? 'analysis_context'
    """)
    op.execute("""
        INSERT INTO ita.roadmap_milestones
            (roadmap_id, external_key, title, required_skills, status, version)
        SELECT r.id, m->>'skill', m->>'skill', jsonb_build_array(m->>'skill'),
               'pending', 1
        FROM ita.roadmaps AS r
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(r.data->'milestones') = 'array'
                 THEN r.data->'milestones' ELSE '[]'::jsonb END
        ) AS m
        WHERE r.data->>'version' = 'pbi023-v1'
            AND length(m->>'skill') BETWEEN 1 AND 128
        ON CONFLICT (roadmap_id, external_key) DO NOTHING
    """)


def downgrade() -> None:
    # The previous schema already supports these rows. Keep recorded progress.
    pass
