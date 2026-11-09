"""merge_migration_heads

Revision ID: 9544e44d3951
Revises: 67e819e5a64b, 9c8b7a6d5e4f
Create Date: 2026-11-09 17:40:37.430134

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "9544e44d3951"
down_revision: str | Sequence[str] | None = ("67e819e5a64b", "9c8b7a6d5e4f")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
