
"""Factory khởi tạo AI provider."""

from app.ai.providers.exceptions import AIConfigurationError
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.config import Settings, settings


def get_ai_provider(
    config: Settings = settings,
) -> OpenAIProvider | OllamaProvider | None:
    """Khởi tạo provider theo cấu hình."""

    if config.ai_provider == "ollama":
        if not config.ai_model:
            return None
        return OllamaProvider(config)

    if config.ai_provider == "openai":
        api_key = config.ai_api_key
        if (
            api_key is None
            or not api_key.get_secret_value().strip()
            or not config.ai_model
        ):
            return None
        return OpenAIProvider(config)

    raise AIConfigurationError(
        "AI provider không được hỗ trợ.",
        provider=config.ai_provider,
    )
