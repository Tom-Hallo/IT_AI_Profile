"""merge AI usage and scoring migration heads

Revision ID: pbi020_scoring_merge
Revises: 7372efb3950b, score_rubric_v2
Create Date: 2026-11-12 11:22:16.490833
"""

from collections.abc import Sequence

revision: str = "pbi020_scoring_merge"
down_revision: str | Sequence[str] | None = ("7372efb3950b", "score_rubric_v2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
