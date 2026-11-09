"""Worker task: Đồng bộ GitHub repositories trong nền (Redis + RQ, PBI-009).

Quy tắc:
- Tham số và kết quả là kiểu JSON đơn giản (chỉ truyền user_id, không truyền token).
- DB session được mở bên trong hàm bằng session_scope().
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.db.session import session_scope
from app.modules.github.service import sync_repositories_for_user
from app.modules.users.models import User

logger = logging.getLogger(__name__)


def sync_user_repositories_task(user_id: int) -> dict[str, Any]:
    """Task RQ thực thi đồng bộ repositories cho người dùng."""
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id không hợp lệ.")

    with session_scope() as db:
        user = db.scalar(select(User).where(User.id == user_id))
        if not user:
            raise ValueError(f"Không tìm thấy người dùng với id={user_id}")

        result = asyncio.run(sync_repositories_for_user(db, user))
        logger.info(f"Hoàn thành đồng bộ repositories cho user_id={user_id}: {result}")
        return {
            "user_id": user_id,
            "status": result.get("status"),
            "synced_count": result.get("synced_count"),
            "last_synced_at": result.get("last_synced_at"),
        }
