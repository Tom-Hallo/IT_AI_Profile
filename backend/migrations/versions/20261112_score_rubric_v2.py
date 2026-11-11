"""Seed the rubric used by report-bound scoring."""

from alembic import op

revision = "score_rubric_v2"
down_revision = "a11jobreport01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO ita.rubric_versions (kind, version, criteria)
        SELECT kind, '2.0.0', jsonb_build_object(
            'weights', jsonb_build_object(
                'code_contribution', 30, 'commit_frequency', 20,
                'pr_contribution', 20, 'complexity', 20, 'confidence', 10
            ),
            'saturation', jsonb_build_object(
                'changed_lines', 200, 'commits', 10, 'pull_requests', 5,
                'distinct_source_files', 8, 'verified_events', 8
            )
        )
        FROM (VALUES ('language'), ('framework')) AS kinds(kind)
        ON CONFLICT (kind, version) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ita.skill_scores WHERE rubric_id IN "
        "(SELECT id FROM ita.rubric_versions WHERE version = '2.0.0')"
    )
    op.execute("DELETE FROM ita.rubric_versions WHERE version = '2.0.0'")
