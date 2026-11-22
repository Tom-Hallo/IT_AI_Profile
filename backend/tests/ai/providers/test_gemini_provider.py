"""Tests for Gemini provider adapter."""

import asyncio
import json

import httpx
import pytest

from app.ai.providers.exceptions import (
    AIConfigurationError,
    AIRateLimitError,
)
from app.ai.providers.gemini_provider import GeminiProvider
from app.core.config import Settings


def run_generate(provider):
    return asyncio.run(
        provider.generate(
            instructions="Analyze repository",
            input_text="print('hello')",
        )
    )


def mock_http_client(monkeypatch, handler):
    original_client = httpx.AsyncClient

    def mock_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client)


def disable_retry_wait(monkeypatch):
    async def no_wait(delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)


def create_provider(**overrides):
    config = {
        "app_env": "development",
        "database_url": "postgresql+psycopg://ita:change-me-dev-only@localhost:5432/it_ai_profile",
        "redis_url": "redis://localhost:6379/0",
        "ai_provider": "gemini",
        "ai_api_key": "dummy-key",
        "ai_model": "gemini-1.5-flash",
        "ai_timeout_seconds": 5,
        **overrides,
    }
    return GeminiProvider(Settings(**config))


def test_gemini_generate_success(monkeypatch):
    disable_retry_wait(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-goog-api-key") == "dummy-key"
        body = json.loads(request.read())
        assert "contents" in body
        assert "system_instruction" in body
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"claims": []}'}],
                            "role": "model",
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 50,
                    "candidatesTokenCount": 20,
                    "totalTokenCount": 70,
                },
                "modelVersion": "gemini-1.5-flash-002",
            },
        )

    mock_http_client(monkeypatch, handler)
    provider = create_provider()
    result = run_generate(provider)

    assert result["text"] == '{"claims": []}'
    assert result["model"] == "gemini-1.5-flash-002"
    assert result["input_tokens"] == 50
    assert result["output_tokens"] == 20
    assert result["total_tokens"] == 70


def test_gemini_missing_api_key():
    provider = create_provider(ai_api_key=None)
    with pytest.raises(AIConfigurationError):
        run_generate(provider)


def test_gemini_rate_limit_error(monkeypatch):
    disable_retry_wait(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit"}})

    mock_http_client(monkeypatch, handler)
    provider = create_provider()
    with pytest.raises(AIRateLimitError):
        run_generate(provider)
