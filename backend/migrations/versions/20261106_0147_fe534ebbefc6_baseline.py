"""baseline

Revision DAU TIEN, CO Y RONG (Blueprint D10, PBI-001).

Khong tao bang nao. Muc dich duy nhat: chung minh chuoi migration chay duoc
(`alembic upgrade head` tao bang he thong `alembic_version` va ghi revision nay vao do).
Bang nghiep vu thuoc cac PBI khac; moi PBI them revision rieng, noi tiep sau revision nay.

Revision ID: fe534ebbefc6
Revises:
Create Date: 2026-11-06 01:47:15.130762
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "fe534ebbefc6"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
