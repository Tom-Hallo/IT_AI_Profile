"""Tests for AI Mentor policy gateway."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.ai.providers.exceptions import AITimeoutError
from app.modules.ai_mentor import policy_gateway


def provider_result():
    """Kết quả giả lập từ AI provider."""
    return {
        "text": "Analysis result",
        "model": "test-model",
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
    }


def setup_audit(monkeypatch):
    """Mock service ghi audit."""
    audit = Mock()
    monkeypatch.setattr(policy_gateway, "record_ai_usage", audit)
    return audit


def test_local_only_does_not_call_provider(monkeypatch):
    """Không cấu hình AI thì không gửi dữ liệu ra ngoài."""

    get_provider = Mock(return_value=None)
    consent_check = Mock()
    audit = setup_audit(monkeypatch)

    monkeypatch.setattr(policy_gateway, "get_ai_provider", get_provider)
    monkeypatch.setattr(policy_gateway, "require_double_consent", consent_check)

    result = asyncio.run(
        policy_gateway.generate_with_policy(
            db=Mock(),
            user_id=1,
            repo_id=10,
            paths=["src/main.py"],
            instructions="Analyze code",
            input_text="print('hello')",
            config=Mock(ai_provider="openai"),
        )
    )

    assert result is None
    get_provider.assert_called_once()
    consent_check.assert_not_called()
    audit.assert_not_called()


def test_missing_consent_blocks_provider(monkeypatch):
    """Thiếu consent thì không được gọi AI."""

    provider = Mock()
    provider.generate = AsyncMock(return_value=provider_result())
    audit = setup_audit(monkeypatch)

    monkeypatch.setattr(policy_gateway, "get_ai_provider", Mock(return_value=provider))
    monkeypatch.setattr(
        policy_gateway,
        "require_double_consent",
        Mock(side_effect=HTTPException(403, "Double consent required")),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            policy_gateway.generate_with_policy(
                db=Mock(),
                user_id=1,
                repo_id=10,
                paths=["src/main.py"],
                instructions="Analyze code",
                input_text="print('hello')",
                config=Mock(ai_provider="openai"),
            )
        )

    assert exc.value.status_code == 403
    provider.generate.assert_not_called()
    audit.assert_not_called()


def test_valid_consent_calls_provider_and_records_usage(monkeypatch):
    """Có consent thì gọi AI và ghi nhận usage."""

    provider = Mock()
    provider.generate = AsyncMock(return_value=provider_result())
    consent_check = Mock()
    audit = setup_audit(monkeypatch)

    monkeypatch.setattr(policy_gateway, "get_ai_provider", Mock(return_value=provider))
    monkeypatch.setattr(policy_gateway, "require_double_consent", consent_check)

    result = asyncio.run(
        policy_gateway.generate_with_policy(
            db=Mock(),
            user_id=1,
            repo_id=10,
            paths=["src/main.py"],
            instructions="Analyze code",
            input_text="print('hello')",
            config=Mock(ai_provider="openai", ai_model="test-model"),
        )
    )

    assert result == "Analysis result"
    assert consent_check.call_count == 1
    assert consent_check.call_args.kwargs["user_id"] == 1
    assert consent_check.call_args.kwargs["repo_id"] == 10
    assert consent_check.call_args.kwargs["provider"] == "openai"
    assert consent_check.call_args.kwargs["paths"] == ["src/main.py"]

    provider.generate.assert_awaited_once_with(
        instructions="Analyze code",
        input_text="print('hello')",
    )

    audit.assert_called_once()
    audit_data = audit.call_args.kwargs
    assert audit_data["user_id"] == 1
    assert audit_data["repository_id"] == 10
    assert audit_data["provider"] == "openai"
    assert audit_data["model"] == "test-model"
    assert audit_data["status"] == "success"
    assert audit_data["input_tokens"] == 100
    assert audit_data["output_tokens"] == 50
    assert audit_data["total_tokens"] == 150
    assert audit_data["duration_ms"] >= 0


def test_provider_timeout_records_failed_usage(monkeypatch):
    """Timeout phải được ghi nhận là failed."""

    provider = Mock()
    provider.generate = AsyncMock(side_effect=AITimeoutError(provider="openai"))
    audit = setup_audit(monkeypatch)

    monkeypatch.setattr(policy_gateway, "get_ai_provider", Mock(return_value=provider))
    monkeypatch.setattr(policy_gateway, "require_double_consent", Mock())

    with pytest.raises(AITimeoutError):
        asyncio.run(
            policy_gateway.generate_with_policy(
                db=Mock(),
                user_id=1,
                repo_id=10,
                paths=["src/main.py"],
                instructions="Analyze code",
                input_text="print('hello')",
                config=Mock(ai_provider="openai", ai_model="test-model"),
            )
        )

    audit.assert_called_once()
    assert audit.call_args.kwargs["status"] == "failed"
    assert audit.call_args.kwargs["input_tokens"] is None
    assert audit.call_args.kwargs["output_tokens"] is None
