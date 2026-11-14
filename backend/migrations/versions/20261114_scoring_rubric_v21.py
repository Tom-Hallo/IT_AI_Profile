"""Seed immutable evidence-based rubric v2.1; retain all v2.0 snapshots."""

from alembic import op

revision = "scoring_rubric_v21"
down_revision = "7a5a48ecd452"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO ita.rubric_versions (kind, version, criteria)
        SELECT kind, '2.1.0', jsonb_build_object(
            'weights', jsonb_build_object(
                'code_contribution', 30, 'commit_frequency', 20,
                'pr_contribution', 20, 'complexity', 20, 'confidence', 10
            ),
            'saturation', jsonb_build_object(
                'changed_lines', 200, 'commits', 10, 'pull_requests', 5,
                'distinct_source_files', 8, 'verified_events', 8
            ),
            'evidence_policy', 'verified_author_nonbot_nonfork_no_merge_frequency',
            'missing_evidence', 'Insufficient',
            'framework_policy', 'insufficient_without_framework_attribution'
        )
        FROM (VALUES ('language'), ('framework')) AS kinds(kind)
        ON CONFLICT (kind, version) DO NOTHING
        """
    )


def downgrade() -> None:
    # Never delete historical skill scores as a side effect of a rollback.
    # Keep rubric rows referenced by snapshots for auditability.
    op.execute(
        """
        DELETE FROM ita.rubric_versions AS rubric
        WHERE rubric.version = '2.1.0'
          AND NOT EXISTS (
            SELECT 1 FROM ita.skill_scores AS score
            WHERE score.rubric_id = rubric.id
          )
        """
    )
