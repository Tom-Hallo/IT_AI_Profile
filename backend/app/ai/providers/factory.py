"""Factory khởi tạo AI provider."""

from app.ai.providers.exceptions import AIConfigurationError
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.config import Settings, settings


def get_ai_provider(
    config: Settings = settings,
) -> OpenAIProvider | None:
    """Trả về provider nếu đã cấu hình, ngược lại dùng local-only."""

    if config.ai_provider != "openai":
        raise AIConfigurationError(
            "AI provider không được hỗ trợ.",
            provider=config.ai_provider,
        )

    api_key = config.ai_api_key
    model = config.ai_model

    if api_key is None or not api_key.get_secret_value().strip() or not model:
        return None

    return OpenAIProvider(config)
