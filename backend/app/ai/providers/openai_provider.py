"""OpenAI provider adapter.

Không ghi API key, prompt hoặc nội dung phản hồi vào log.
"""

from typing import TypedDict

import httpx

from app.ai.prompts.security import (
    SYSTEM_SECURITY_INSTRUCTIONS,
    build_secure_input,
)
from app.ai.providers.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
)
from app.core.config import Settings


class AIProviderResult(TypedDict):
    """Kết quả AI và metadata sử dụng."""

    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class OpenAIProvider:
    """Adapter gọi OpenAI Responses API."""

    API_URL = "https://api.openai.com/v1/responses"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        *,
        instructions: str,
        input_text: str,
    ) -> AIProviderResult:
        """Gửi yêu cầu và trả về nội dung cùng token usage."""

        api_key = self.settings.ai_api_key
        model = self.settings.ai_model

        if api_key is None or not api_key.get_secret_value().strip() or not model:
            raise AIConfigurationError(provider="openai")

        if not instructions.strip() or not input_text.strip():
            raise ValueError("Instructions và input không được để trống.")

        headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "instructions": (
                SYSTEM_SECURITY_INSTRUCTIONS + "\n\nAPPLICATION TASK:\n" + instructions
            ),
            "input": build_secure_input(input_text),
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.ai_timeout_seconds
            ) as client:
                response = await client.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

        except httpx.TimeoutException:
            raise AITimeoutError(provider="openai") from None

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise AIRateLimitError(provider="openai") from None

            raise AIProviderError(
                f"AI provider trả về lỗi HTTP {exc.response.status_code}.",
                provider="openai",
                retryable=exc.response.status_code >= 500,
            ) from None

        except (httpx.RequestError, ValueError):
            raise AIProviderError(
                "Không thể kết nối hoặc đọc phản hồi từ AI provider.",
                provider="openai",
                retryable=True,
            ) from None

        if not isinstance(result, dict):
            raise AIProviderError(
                "AI provider trả về dữ liệu không hợp lệ.",
                provider="openai",
            )

        output_text = result.get("output_text")

        if not isinstance(output_text, str) or not output_text.strip():
            output_parts: list[str] = []

            for item in result.get("output", []):
                if not isinstance(item, dict):
                    continue

                for content in item.get("content", []):
                    if (
                        isinstance(content, dict)
                        and content.get("type") == "output_text"
                    ):
                        text = content.get("text")
                        if isinstance(text, str):
                            output_parts.append(text)

            output_text = "\n".join(output_parts).strip()

        if not output_text:
            raise AIProviderError(
                "AI provider trả về phản hồi không hợp lệ.",
                provider="openai",
            )

        usage = result.get("usage")
        if not isinstance(usage, dict):
            usage = {}

        def read_token(name: str) -> int | None:
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool):
                return value if value >= 0 else None
            return None

        actual_model = result.get("model")
        if not isinstance(actual_model, str) or not actual_model:
            actual_model = model

        return {
            "text": output_text.strip(),
            "model": actual_model,
            "input_tokens": read_token("input_tokens"),
            "output_tokens": read_token("output_tokens"),
            "total_tokens": read_token("total_tokens"),
        }
