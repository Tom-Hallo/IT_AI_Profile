"""Tests for OpenAI provider adapter."""

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from app.ai.providers.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
)
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.config import Settings


def make_provider(handler, *, api_key="test-key", model="test-model"):
    """Tạo provider với HTTP transport giả lập."""

    transport = httpx.MockTransport(handler)

    class MockAsyncClient:
        async def __aenter__(self):
            self.client = httpx.AsyncClient(transport=transport)
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

        def __getattr__(self, name):
            return getattr(self.client, name)

    provider = OpenAIProvider(
        Settings(
            ai_provider="openai",
            ai_api_key=SecretStr(api_key) if api_key else None,
            ai_model=model,
            ai_timeout_seconds=5,
        )
    )

    provider_client = MockAsyncClient
    original_client = httpx.AsyncClient

    return provider, transport, provider_client, original_client


def run_generate(provider, monkeypatch):
    """Thực thi generate bằng HTTP client giả lập."""

    async def execute():
        return await provider.generate(
            instructions="Analyze repository",
            input_text="print('hello')",
        )

    return asyncio.run(execute())


def test_generate_returns_text_and_usage(monkeypatch):
    """Phản hồi thành công phải trả về text và token usage."""

    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        body = request.read().decode()
        assert "Analyze repository" not in body or "instructions" in body

        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "output_text": "Analysis result",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )

    provider = OpenAIProvider(
        Settings(
            ai_provider="openai",
            ai_api_key=SecretStr("test-key"),
            ai_model="test-model",
            ai_timeout_seconds=5,
        )
    )

    original_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client)

    result = run_generate(provider, monkeypatch)

    assert result["text"] == "Analysis result"
    assert result["model"] == "test-model"
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50
    assert result["total_tokens"] == 150


def test_missing_api_key_raises_configuration_error():
    """Thiếu API key phải báo lỗi cấu hình."""

    provider = OpenAIProvider(
        Settings(
            ai_provider="openai",
            ai_api_key=None,
            ai_model="test-model",
        )
    )

    with pytest.raises(AIConfigurationError):
        run_generate(provider, None)


def test_http_429_raises_rate_limit(monkeypatch):
    """HTTP 429 phải được chuyển thành rate limit error."""

    def handler(request):
        return httpx.Response(429, json={"error": "rate limited"})

    provider = OpenAIProvider(
        Settings(
            ai_provider="openai",
            ai_api_key=SecretStr("test-key"),
            ai_model="test-model",
        )
    )

    original_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client)

    with pytest.raises(AIRateLimitError):
        run_generate(provider, monkeypatch)


def test_http_500_raises_retryable_provider_error(monkeypatch):
    """HTTP 500 phải được đánh dấu có thể retry."""

    def handler(request):
        return httpx.Response(500, json={"error": "server error"})

    provider = OpenAIProvider(
        Settings(
            ai_provider="openai",
            ai_api_key=SecretStr("test-key"),
            ai_model="test-model",
        )
    )

    original_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client)

    with pytest.raises(AIProviderError) as exc:
        run_generate(provider, monkeypatch)

    assert exc.value.retryable is True


def test_invalid_response_raises_provider_error(monkeypatch):
    """Phản hồi không có nội dung phải báo lỗi."""

    def handler(request):
        return httpx.Response(
            200,
            json={"model": "test-model", "output": [], "usage": {}},
        )

    provider = OpenAIProvider(
        Settings(
            ai_provider="openai",
            ai_api_key=SecretStr("test-key"),
            ai_model="test-model",
        )
    )

    original_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client)

    with pytest.raises(AIProviderError):
        run_generate(provider, monkeypatch)
