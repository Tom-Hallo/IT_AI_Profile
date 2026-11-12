"""Worker task: Đồng bộ GitHub repositories trong nền (Redis + RQ, PBI-009).

Quy tắc:
- Tham số và kết quả là kiểu JSON đơn giản (chỉ truyền user_id, không truyền token).
- DB session được mở bên trong hàm bằng session_scope().
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from rq import get_current_job
from sqlalchemy import select

from app.db.session import session_scope
from app.modules.github.schemas import RepositoryVisibility
from app.modules.github.service import set_sync_status_cache, sync_repositories_for_user
from app.modules.users.models import User

logger = logging.getLogger(__name__)


def sync_user_repositories_task(
    user_id: int, visibility: RepositoryVisibility | None = None,
) -> dict[str, Any]:
    """Task RQ thực thi đồng bộ repositories cho người dùng."""
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id không hợp lệ.")

    try:
        with session_scope() as db:
            user = db.scalar(select(User).where(User.id == user_id))
            if not user:
                raise ValueError(f"Không tìm thấy người dùng với id={user_id}")

            options = {"visibility": visibility} if visibility else {}
            job = get_current_job()
            if job is not None:
                options["job_id"] = job.id
            result = asyncio.run(sync_repositories_for_user(db, user, **options))
            logger.info(
                f"Hoàn thành đồng bộ repositories cho user_id={user_id}: {result}"
            )
            return {
                "user_id": user_id,
                "status": result.get("status"),
                "synced_count": result.get("synced_count"),
                "synced_visibility": result.get("synced_visibility"),
                "last_synced_at": result.get("last_synced_at"),
            }
    except BaseException as exc:
        logger.exception(
            "Lỗi khi thực thi worker task sync_user_repositories_task cho user_id=%s",
            user_id,
        )
        error_msg = (
            "Quá thời gian thực thi tác vụ đồng bộ (Job timeout)."
            if "Timeout" in type(exc).__name__
            else f"Đồng bộ repository thất bại: {exc}"
        )
        set_sync_status_cache(
            user_id=user_id,
            status="failed",
            error_message=error_msg,
        )
        raise
