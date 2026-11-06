"""baseline

Revision ĐẦU TIÊN, CỐ Ý RỖNG (Blueprint D10, PBI-001).

Không tạo bảng nào. Mục đích duy nhất: chứng minh chuỗi migration chạy được
(`alembic upgrade head` tạo bảng hệ thống `alembic_version` và ghi revision này vào đó).
22 bảng nghiệp vụ trong DBML thuộc các PBI khác; mỗi PBI thêm revision riêng, nối tiếp
sau revision này.

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
