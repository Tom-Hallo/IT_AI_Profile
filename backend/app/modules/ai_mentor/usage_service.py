"""Service ghi nhận metadata sử dụng AI provider."""

import logging
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import session_scope
from app.modules.ai_mentor.usage_models import AIUsageLog

logger = logging.getLogger(__name__)


def record_ai_usage(
    *,
    user_id: int,
    repository_id: int | None,
    provider: str,
    model: str,
    status: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    duration_ms: int | None = None,
) -> None:
    """Ghi metadata AI bằng transaction độc lập.

    Không lưu prompt, response, API key hoặc mã nguồn.
    Lỗi ghi audit không làm lộ dữ liệu nhạy cảm.
    """
    try:
        with session_scope() as db:
            db.add(
                AIUsageLog(
                    user_id=user_id,
                    repository_id=repository_id,
                    provider=provider,
                    model=model,
                    status=status,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    duration_ms=duration_ms,
                )
            )
    except SQLAlchemyError:
        logger.exception("Failed to persist AI usage audit metadata")


def count_ai_requests_today(*, user_id: int, provider: str) -> int:
    """Đếm số request AI của user trong ngày UTC hiện tại."""
    now = datetime.now(UTC)
    start_of_day = datetime.combine(
        now.date(),
        time.min,
        tzinfo=UTC,
    )
    start_of_next_day = start_of_day + timedelta(days=1)

    try:
        with session_scope() as db:
            statement = (
                select(func.count())
                .select_from(AIUsageLog)
                .where(
                    AIUsageLog.user_id == user_id,
                    AIUsageLog.provider == provider,
                    AIUsageLog.created_at >= start_of_day,
                    AIUsageLog.created_at < start_of_next_day,
                )
            )
            return db.scalar(statement) or 0
    except SQLAlchemyError:
        logger.exception("Failed to count AI usage requests")
        raise
