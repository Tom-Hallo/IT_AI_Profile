"""Policy gateway kiểm soát dữ liệu trước khi gửi tới AI."""

import logging
from time import perf_counter

from sqlalchemy.orm import Session

from app.ai.providers import (
    AIProviderError,
    get_ai_provider,
)
from app.core.config import Settings, settings
from app.modules.ai_mentor.usage_service import record_ai_usage
from app.modules.consent.service import require_double_consent

logger = logging.getLogger(__name__)


async def generate_with_policy(
    *,
    db: Session,
    user_id: int,
    repo_id: int,
    paths: list[str],
    instructions: str,
    input_text: str,
    config: Settings = settings,
) -> str | None:
    """Kiểm tra consent, gọi AI và ghi metadata audit.

    Trả về None nếu AI chưa được cấu hình (local-only).
    """

    provider = get_ai_provider(config)

    if provider is None:
        return None

    # Kiểm tra consent trước mọi hoạt động gửi dữ liệu ra ngoài.
    require_double_consent(
        db=db,
        user_id=user_id,
        repo_id=repo_id,
        provider=config.ai_provider,
        paths=paths,
    )

    started_at = perf_counter()
    status = "failed"
    result = None

    try:
        result = await provider.generate(
            instructions=instructions,
            input_text=input_text,
        )
        status = "success"
        return result["text"]

    except AIProviderError:
        status = "failed"
        raise

    finally:
        duration_ms = int((perf_counter() - started_at) * 1000)

        record_ai_usage(
            user_id=user_id,
            repository_id=repo_id,
            provider=config.ai_provider,
            model=(
                result["model"] if result is not None else config.ai_model or "unknown"
            ),
            status=status,
            input_tokens=(result["input_tokens"] if result is not None else None),
            output_tokens=(result["output_tokens"] if result is not None else None),
            total_tokens=(result["total_tokens"] if result is not None else None),
            duration_ms=duration_ms,
        )


__all__ = [
    "generate_with_policy",
    "AIProviderError",
]
