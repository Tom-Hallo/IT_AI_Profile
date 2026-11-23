"""Seed framework PR-or-commit rubric v2.2 without changing historical scores."""

from alembic import op

revision = "framework_scoring_v22"
down_revision = "add_gemini_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO ita.rubric_versions (kind, version, criteria)
        VALUES ('framework', '2.2.0', jsonb_build_object(
            'weights', jsonb_build_object(
                'code_contribution', 40,
                'complexity', 20,
                'verified_activity', 30,
                'confidence', 10
            ),
            'saturation', jsonb_build_object(
                'changed_lines', 200,
                'commits', 10,
                'pull_requests', 5,
                'distinct_source_files', 8,
                'verified_events', 8
            ),
            'evidence_policy', 'source_code_plus_verified_pr_or_nonmerge_commit',
            'missing_evidence', 'Insufficient',
            'partial_file_evidence', 'reduce_confidence',
            'framework_policy', 'verified_source_overlap_required'
        ))
        ON CONFLICT (kind, version) DO NOTHING
        """
    )


def downgrade() -> None:
    # Keep v2.2 rubric if a saved score references it.
    op.execute(
        """
        DELETE FROM ita.rubric_versions AS rubric
        WHERE rubric.kind = 'framework'
          AND rubric.version = '2.2.0'
          AND NOT EXISTS (
            SELECT 1 FROM ita.skill_scores AS score
            WHERE score.rubric_id = rubric.id
          )
        """
    )
