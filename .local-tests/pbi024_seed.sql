BEGIN;

INSERT INTO ita.roadmaps
    (id, user_id, title, description, data)
VALUES (
    900024,
    1,
    'PBI-024 E2E Test',
    'Integration test roadmap',
    jsonb_build_object(
        'analysis_context',
        jsonb_build_object(
            'scope', 'public',
            'rubric', 'v1',
            'period', 'last-90-days'
        )
    )
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO ita.roadmap_milestones
    (roadmap_id, external_key, title, required_skills, status)
VALUES
    (900024, 'python', 'Python Fundamentals',
     '["Python"]'::jsonb, 'pending'),
    (900024, 'fastapi', 'FastAPI Development',
     '["FastAPI"]'::jsonb, 'in_progress'),
    (900024, 'postgres', 'PostgreSQL Development',
     '["PostgreSQL"]'::jsonb, 'pending')
ON CONFLICT (roadmap_id, external_key) DO NOTHING;

COMMIT;
