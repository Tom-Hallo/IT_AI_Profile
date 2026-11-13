"""OpenAI provider adapter.

Không ghi API key, prompt hoặc nội dung phản hồi vào log.
"""

import asyncio
from collections.abc import Callable
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

    # Tối đa 3 lần gửi request, bao gồm lần đầu.
    MAX_ATTEMPTS = 3

    # Thời gian chờ giữa các lần retry: 0.25s, 0.5s.
    RETRY_BASE_DELAY = 0.25
    RETRY_MAX_DELAY = 1.0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        before_send: Callable[[], None] | None = None,
    ) -> AIProviderResult:
        """Gửi yêu cầu và trả về nội dung cùng token usage."""

        api_key = self.settings.ai_api_key
        model = self.settings.ai_model

        if api_key is None or not api_key.get_secret_value().strip() or not model:
            raise AIConfigurationError(provider="openai")

        if not instructions.strip() or not input_text.strip():
            raise ValueError("Instructions và input không được để trống.")

        if len(input_text) > self.settings.ai_max_input_chars:
            raise AIProviderError(
                "Nội dung đầu vào vượt quá giới hạn cho phép.",
                provider="openai",
                retryable=False,
            )

        headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "instructions": (
                SYSTEM_SECURITY_INSTRUCTIONS + "\n\nAPPLICATION TASK:\n" + instructions
            ),
            "input": build_secure_input(input_text),
        }

        if before_send is not None:
            payload["store"] = False

        result = None
        last_error: AIProviderError | None = None

        async with httpx.AsyncClient(
            timeout=self.settings.ai_timeout_seconds
        ) as client:
            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    if before_send is not None:
                        before_send()
                    response = await client.post(
                        self.API_URL,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    result = response.json()
                    break

                except httpx.TimeoutException:
                    last_error = AITimeoutError(provider="openai")

                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code

                    if status_code == 429:
                        raise AIRateLimitError(provider="openai") from None

                    if status_code < 500:
                        raise AIProviderError(
                            f"AI provider trả về lỗi HTTP {status_code}.",
                            provider="openai",
                            retryable=False,
                        ) from None

                    last_error = AIProviderError(
                        f"AI provider trả về lỗi HTTP {status_code}.",
                        provider="openai",
                        retryable=True,
                    )

                except httpx.RequestError:
                    last_error = AIProviderError(
                        "Không thể kết nối đến AI provider.",
                        provider="openai",
                        retryable=True,
                    )

                except ValueError:
                    raise AIProviderError(
                        "AI provider trả về dữ liệu JSON không hợp lệ.",
                        provider="openai",
                        retryable=False,
                    ) from None

                if attempt < self.MAX_ATTEMPTS - 1:
                    delay = min(
                        self.RETRY_BASE_DELAY * (2**attempt),
                        self.RETRY_MAX_DELAY,
                    )
                    await asyncio.sleep(delay)

        if result is None:
            if last_error is not None:
                raise last_error

            raise AIProviderError(
                "Không thể hoàn thành yêu cầu đến AI provider.",
                provider="openai",
                retryable=False,
            )

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
