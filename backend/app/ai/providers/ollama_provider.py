
"""Ollama provider adapter.

Không ghi prompt, nội dung code hoặc dữ liệu riêng tư vào log.
"""

import asyncio
from typing import Any

import httpx

from app.ai.prompts.security import (
    SYSTEM_SECURITY_INSTRUCTIONS,
    build_secure_input,
)
from app.ai.providers.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AITimeoutError,
)
from app.ai.providers.openai_provider import AIProviderResult
from app.core.config import Settings


class OllamaProvider:
    """Adapter gọi Ollama native Chat API."""

    MAX_ATTEMPTS = 3
    RETRY_BASE_DELAY = 0.25
    RETRY_MAX_DELAY = 1.0

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        *,
        instructions: str,
        input_text: str,
    ) -> AIProviderResult:
        """Gửi yêu cầu tới Ollama và trả về nội dung cùng token usage."""

        model = self.settings.ai_model

        if not model:
            raise AIConfigurationError(
                "Ollama model chưa được cấu hình.",
                provider="ollama",
            )

        if not instructions.strip() or not input_text.strip():
            raise ValueError("Instructions và input không được để trống.")

        if len(input_text) > self.settings.ai_max_input_chars:
            raise AIProviderError(
                "AI input vượt quá giới hạn cho phép.",
                provider="ollama",
                retryable=False,
            )

        base_url = self.settings.ai_base_url.rstrip("/")
        url = f"{base_url}/api/chat"

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        SYSTEM_SECURITY_INSTRUCTIONS
                        + "\n\nAPPLICATION TASK:\n"
                        + instructions
                    ),
                },
                {
                    "role": "user",
                    "content": build_secure_input(input_text),
                },
            ],
            "stream": False,
            "options": {
                "num_predict": self.settings.ai_max_output_tokens,
            },
        }

        timeout = httpx.Timeout(self.settings.ai_timeout_seconds)

        for attempt in range(self.MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, json=payload)

                if response.status_code >= 500:
                    raise AIProviderError(
                        "Ollama server gặp lỗi.",
                        provider="ollama",
                        retryable=True,
                    )

                if response.status_code >= 400:
                    raise AIProviderError(
                        "Ollama từ chối yêu cầu.",
                        provider="ollama",
                        retryable=False,
                    )

                data: dict[str, Any] = response.json()
                message = data.get("message") or {}
                content = message.get("content")

                if not isinstance(content, str):
                    raise AIProviderError(
                        "Ollama trả về dữ liệu không hợp lệ.",
                        provider="ollama",
                        retryable=False,
                    )

                input_tokens = data.get("prompt_eval_count")
                output_tokens = data.get("eval_count")

                return {
                    "text": content,
                    "model": str(data.get("model") or model),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": (
                        input_tokens + output_tokens
                        if isinstance(input_tokens, int)
                        and isinstance(output_tokens, int)
                        else None
                    ),
                }

            except httpx.TimeoutException:
                if attempt == self.MAX_ATTEMPTS - 1:
                    raise AITimeoutError(provider="ollama") from None

            except httpx.RequestError:
                if attempt == self.MAX_ATTEMPTS - 1:
                    raise AIProviderError(
                        "Không thể kết nối Ollama server.",
                        provider="ollama",
                        retryable=True,
                    ) from None

            except AIProviderError as exc:
                if not exc.retryable or attempt == self.MAX_ATTEMPTS - 1:
                    raise

            if attempt < self.MAX_ATTEMPTS - 1:
                delay = min(
                    self.RETRY_BASE_DELAY * (2**attempt),
                    self.RETRY_MAX_DELAY,
                )
                await asyncio.sleep(delay)

        raise AIProviderError(
            "Ollama request thất bại.",
            provider="ollama",
            retryable=True,
        )
