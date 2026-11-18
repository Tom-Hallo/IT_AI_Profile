"""Policy gateway kiểm soát dữ liệu trước khi gửi tới AI."""

import json
import logging
from collections.abc import Mapping
from time import perf_counter

from sqlalchemy.orm import Session

from app.ai.providers import (
    AIProviderError,
    get_ai_provider,
)
from app.core.config import Settings, settings
from app.modules.ai_mentor.usage_service import (
    count_ai_requests_today,
    record_ai_usage,
)
from app.modules.analysis.filters import is_ignored_path, is_safe_path
from app.modules.consent.service import require_double_consent

logger = logging.getLogger(__name__)


def _prepare_scoped_input(files: Mapping[str, str]) -> tuple[list[str], str]:
    """Kiểm tra đường dẫn và đóng gói nội dung theo từng file."""

    if not isinstance(files, Mapping) or not files:
        raise ValueError("Phải cung cấp ít nhất một file để phân tích.")

    if len(files) > 100:
        raise ValueError("Số lượng file gửi AI không được vượt quá 100.")

    validated_files = []

    for path, content in files.items():
        if not isinstance(path, str) or not is_safe_path(path):
            raise ValueError(f"Đường dẫn file không an toàn: {path!r}")

        if is_ignored_path(path):
            raise ValueError(f"File không được phép gửi tới AI: {path}")

        if not isinstance(content, str):
            raise ValueError(f"Nội dung file không hợp lệ: {path}")

        validated_files.append(
            {
                "path": path,
                "content": content,
            }
        )

    validated_files.sort(key=lambda item: item["path"])

    paths = [item["path"] for item in validated_files]
    input_text = json.dumps(
        {"files": validated_files},
        ensure_ascii=False,
    )

    return paths, input_text


async def generate_with_policy(
    *,
    db: Session,
    user_id: int,
    repo_id: int,
    files: Mapping[str, str],
    instructions: str,
    config: Settings = settings,
) -> str | None:
    """Kiểm tra consent và dữ liệu file trước khi gọi AI.

    Trả về None nếu AI chưa được cấu hình (local-only).
    """

    provider = get_ai_provider(config)

    if provider is None:
        return None

    # Đường dẫn được lấy trực tiếp từ dữ liệu file, không nhận paths riêng.
    paths, input_text = _prepare_scoped_input(files)

    # Kiểm tra consent trước mọi hoạt động gửi dữ liệu ra ngoài.
    require_double_consent(
        db=db,
        user_id=user_id,
        repo_id=repo_id,
        provider=config.ai_provider,
        paths=paths,
    )

    request_count = count_ai_requests_today(
        user_id=user_id,
        provider=config.ai_provider,
    )

    if request_count >= config.ai_max_requests_per_day:
        from app.ai.providers.exceptions import AICostLimitError

        raise AICostLimitError(
            "Bạn đã vượt quá giới hạn request AI trong ngày.",
            provider=config.ai_provider,
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
