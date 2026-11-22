"""Gemini provider adapter.

Không ghi API key, prompt hoặc nội dung phản hồi vào log.
"""

import asyncio
from collections.abc import Callable
from typing import Any

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
from app.ai.providers.openai_provider import AIProviderResult
from app.core.config import Settings


class GeminiProvider:
    """Adapter gọi Google Gemini REST API."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

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
        before_send: Callable[[], None] | None = None,
    ) -> AIProviderResult:
        """Gửi yêu cầu tới Google Gemini và trả về nội dung cùng token usage."""

        api_key = self.settings.ai_api_key
        model = self.settings.ai_model

        if api_key is None or not api_key.get_secret_value().strip() or not model:
            raise AIConfigurationError(provider="gemini")

        # Tự động chuyển đổi các model cũ/quota thấp sang model hoạt động ổn định nhất
        if model in (
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-3-flash-preview",
            "gemini-flash-latest",
        ):
            model = "gemini-3.1-flash-lite"

        if not instructions.strip() or not input_text.strip():
            raise ValueError("Instructions và input không được để trống.")

        if len(input_text) > self.settings.ai_max_input_chars:
            raise AIProviderError(
                "Nội dung đầu vào vượt quá giới hạn cho phép.",
                provider="gemini",
                retryable=False,
            )

        headers = {
            "x-goog-api-key": api_key.get_secret_value(),
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "system_instruction": {
                "parts": [
                    {
                        "text": (
                            SYSTEM_SECURITY_INSTRUCTIONS
                            + "\n\nAPPLICATION TASK:\n"
                            + instructions
                        )
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": build_secure_input(input_text)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": self.settings.ai_max_output_tokens,
                "responseMimeType": "application/json",
            },
        }

        url = f"{self.API_BASE}/{model}:generateContent"

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
                        url,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    result = response.json()
                    break

                except httpx.TimeoutException:
                    last_error = AITimeoutError(provider="gemini")

                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code

                    if status_code == 429:
                        raise AIRateLimitError(provider="gemini") from None

                    if status_code < 500:
                        raise AIProviderError(
                            f"AI provider trả về lỗi HTTP {status_code}.",
                            provider="gemini",
                            retryable=False,
                        ) from None

                    last_error = AIProviderError(
                        f"AI provider trả về lỗi HTTP {status_code}.",
                        provider="gemini",
                        retryable=True,
                    )

                except httpx.RequestError:
                    last_error = AIProviderError(
                        "Không thể kết nối đến AI provider.",
                        provider="gemini",
                        retryable=True,
                    )

                except ValueError:
                    raise AIProviderError(
                        "AI provider trả về dữ liệu JSON không hợp lệ.",
                        provider="gemini",
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
                provider="gemini",
                retryable=False,
            )

        if not isinstance(result, dict):
            raise AIProviderError(
                "AI provider trả về dữ liệu không hợp lệ.",
                provider="gemini",
            )

        candidates = result.get("candidates") or []
        output_text = ""
        if candidates and isinstance(candidates, list):
            first_candidate = candidates[0]
            if isinstance(first_candidate, dict):
                content = first_candidate.get("content") or {}
                if isinstance(content, dict):
                    parts = content.get("parts") or []
                    if parts and isinstance(parts, list):
                        output_parts = [
                            p.get("text", "")
                            for p in parts
                            if isinstance(p, dict) and p.get("text")
                        ]
                        output_text = "\n".join(output_parts).strip()

        if not output_text.strip():
            raise AIProviderError(
                "AI provider trả về phản hồi rỗng.",
                provider="gemini",
                retryable=False,
            )

        usage = result.get("usageMetadata") or {}
        input_tokens = usage.get("promptTokenCount")
        output_tokens = usage.get("candidatesTokenCount")
        total_tokens = usage.get("totalTokenCount")

        return {
            "text": output_text,
            "model": str(result.get("modelVersion") or model),
            "input_tokens": input_tokens if isinstance(input_tokens, int) else None,
            "output_tokens": output_tokens if isinstance(output_tokens, int) else None,
            "total_tokens": total_tokens if isinstance(total_tokens, int) else None,
        }
