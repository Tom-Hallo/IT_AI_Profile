"""merge PBI-015 findings and AI usage audit heads

Revision ID: 7372efb3950b
Revises: 7ebc77ef44c4, pbi015findings01
Create Date: 2026-11-11 13:34:46.694542
"""

from collections.abc import Sequence

revision: str = "7372efb3950b"
down_revision: str | Sequence[str] | None = ("7ebc77ef44c4", "pbi015findings01")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
