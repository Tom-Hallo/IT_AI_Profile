"""GET /api/v1/health (Blueprint mục 7.1).

- Công khai, không cần đăng nhập.
- Mỗi dependency tối đa 3 giây; hai kiểm tra chạy song song nên tổng < 5 giây.
- Không bao giờ trả thông báo lỗi gốc, stack trace, URL kết nối hay tên người dùng DB.
"""

import asyncio
import logging
from collections.abc import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core import redis as redis_core
from app.core.config import APP_NAME, APP_VERSION
from app.db import session as db_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 3


async def _run_check(name: str, check: Callable[[], None]) -> tuple[str, str]:
    try:
        # Hàm kiểm tra là đồng bộ (RQ/psycopg đồng bộ, D07) nên chạy trong thread.
        await asyncio.wait_for(asyncio.to_thread(check), timeout=CHECK_TIMEOUT_SECONDS)
        return name, "ok"
    except Exception as exc:  # noqa: BLE001 - mọi lỗi đều quy về "fail"
        # Chỉ ghi TÊN loại lỗi; thông điệp lỗi gốc có thể chứa URL/mật khẩu.
        logger.warning("Health check '%s' thất bại: %s", name, type(exc).__name__)
        return name, "fail"


@router.get("/health")
async def health() -> JSONResponse:
    # Tra cứu hàm tại thời điểm gọi (qua module) để test có thể thay thế.
    results = await asyncio.gather(
        _run_check("database", db_session.check_database),
        _run_check("redis", redis_core.check_redis),
    )
    checks = dict(results)
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "service": APP_NAME,
            "version": APP_VERSION,
            "checks": checks,
        },
    )
