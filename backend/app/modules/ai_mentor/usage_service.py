"""Service ghi nhận metadata sử dụng AI provider."""

import logging

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
