"""Tests for AI Mentor policy gateway."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.ai.providers.exceptions import AICostLimitError, AITimeoutError
from app.modules.ai_mentor import policy_gateway
from app.modules.consent import service as consent_service


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


def setup_provider(monkeypatch):
    """Khởi tạo AI provider giả lập."""
    provider = Mock()
    provider.generate = AsyncMock(return_value=provider_result())
    monkeypatch.setattr(policy_gateway, "get_ai_provider", Mock(return_value=provider))
    return provider


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
            files={"src/main.py": "print('hello')"},
            instructions="Analyze code",
            config=Mock(ai_provider="openai"),
        )
    )

    assert result is None
    get_provider.assert_called_once()
    consent_check.assert_not_called()
    audit.assert_not_called()


def test_missing_consent_blocks_provider(monkeypatch):
    """Thiếu consent thì không được gọi AI."""

    provider = setup_provider(monkeypatch)
    audit = setup_audit(monkeypatch)

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
                files={"src/main.py": "print('hello')"},
                instructions="Analyze code",
                config=Mock(ai_provider="openai"),
            )
        )

    assert exc.value.status_code == 403
    provider.generate.assert_not_called()
    audit.assert_not_called()


def test_scope_mismatch_blocks_provider(monkeypatch):
    """File ngoài phạm vi consent phải bị chặn trước khi gọi AI."""

    provider = setup_provider(monkeypatch)
    audit = setup_audit(monkeypatch)

    repo = Mock(private=True)

    access_consent = SimpleNamespace(
        granted=True,
        policy_version=consent_service.POLICY_VERSION,
        revoked_at=None,
        scope=["src/a.py"],
    )
    external_consent = SimpleNamespace(
        granted=True,
        policy_version=consent_service.POLICY_VERSION,
        revoked_at=None,
        scope=["src/a.py"],
    )

    db = Mock()
    db.scalar.side_effect = [access_consent, external_consent]

    monkeypatch.setattr(
        consent_service,
        "owned_repo",
        Mock(return_value=repo),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            policy_gateway.generate_with_policy(
                db=db,
                user_id=1,
                repo_id=10,
                files={
                    "src/a.py": "print('allowed')",
                    "src/b.py": "print('not allowed')",
                },
                instructions="Analyze code",
                config=Mock(ai_provider="openai"),
            )
        )

    assert exc.value.status_code == 403
    assert "Scope not approved" in str(exc.value.detail)
    assert db.scalar.call_count == 2
    provider.generate.assert_not_called()
    audit.assert_not_called()


def test_valid_consent_calls_provider_and_records_usage(monkeypatch):
    """Có consent thì gọi AI và ghi nhận usage."""

    provider = setup_provider(monkeypatch)
    consent_check = Mock()
    audit = setup_audit(monkeypatch)

    monkeypatch.setattr(
        policy_gateway,
        "count_ai_requests_today",
        Mock(return_value=0),
    )
    monkeypatch.setattr(
        policy_gateway,
        "require_double_consent",
        consent_check,
    )

    result = asyncio.run(
        policy_gateway.generate_with_policy(
            db=Mock(),
            user_id=1,
            repo_id=10,
            files={"src/main.py": "print('hello')"},
            instructions="Analyze code",
            config=Mock(
                ai_provider="openai",
                ai_model="test-model",
                ai_max_requests_per_day=50,
            ),
        )
    )

    assert result == "Analysis result"
    assert consent_check.call_count == 1
    assert consent_check.call_args.kwargs["user_id"] == 1
    assert consent_check.call_args.kwargs["repo_id"] == 10
    assert consent_check.call_args.kwargs["provider"] == "openai"
    assert consent_check.call_args.kwargs["paths"] == ["src/main.py"]

    provider.generate.assert_awaited_once()
    call_data = provider.generate.call_args.kwargs

    assert call_data["instructions"] == "Analyze code"
    assert json.loads(call_data["input_text"]) == {
        "files": [
            {
                "path": "src/main.py",
                "content": "print('hello')",
            }
        ]
    }

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


def test_daily_request_limit_blocks_provider(monkeypatch):
    """Đạt giới hạn request trong ngày thì không được gọi AI."""

    provider = setup_provider(monkeypatch)
    audit = setup_audit(monkeypatch)

    count_requests = Mock(return_value=50)
    monkeypatch.setattr(
        policy_gateway,
        "count_ai_requests_today",
        count_requests,
    )
    monkeypatch.setattr(
        policy_gateway,
        "require_double_consent",
        Mock(),
    )

    with pytest.raises(AICostLimitError):
        asyncio.run(
            policy_gateway.generate_with_policy(
                db=Mock(),
                user_id=1,
                repo_id=10,
                files={"src/main.py": "print('hello')"},
                instructions="Analyze code",
                config=Mock(
                    ai_provider="openai",
                    ai_model="test-model",
                    ai_max_requests_per_day=50,
                ),
            )
        )

    count_requests.assert_called_once_with(
        user_id=1,
        provider="openai",
    )
    provider.generate.assert_not_called()
    audit.assert_not_called()


def test_provider_timeout_records_failed_usage(monkeypatch):
    """Timeout phải được ghi nhận là failed."""

    provider = setup_provider(monkeypatch)
    provider.generate.side_effect = AITimeoutError(provider="openai")
    audit = setup_audit(monkeypatch)

    monkeypatch.setattr(
        policy_gateway,
        "count_ai_requests_today",
        Mock(return_value=0),
    )
    monkeypatch.setattr(
        policy_gateway,
        "require_double_consent",
        Mock(),
    )

    with pytest.raises(AITimeoutError):
        asyncio.run(
            policy_gateway.generate_with_policy(
                db=Mock(),
                user_id=1,
                repo_id=10,
                files={"src/main.py": "print('hello')"},
                instructions="Analyze code",
                config=Mock(
                    ai_provider="openai",
                    ai_model="test-model",
                    ai_max_requests_per_day=50,
                ),
            )
        )

    audit.assert_called_once()
    assert audit.call_args.kwargs["status"] == "failed"
    assert audit.call_args.kwargs["input_tokens"] is None
    assert audit.call_args.kwargs["output_tokens"] is None


def test_unsafe_path_blocks_provider(monkeypatch):
    """Đường dẫn traversal không được gửi tới AI."""

    provider = setup_provider(monkeypatch)

    with pytest.raises(ValueError):
        asyncio.run(
            policy_gateway.generate_with_policy(
                db=Mock(),
                user_id=1,
                repo_id=10,
                files={"../secret.txt": "private data"},
                instructions="Analyze code",
                config=Mock(ai_provider="openai"),
            )
        )

    provider.generate.assert_not_called()


def test_ignored_file_blocks_provider(monkeypatch):
    """File trong thư mục bị loại trừ không được gửi tới AI."""

    provider = setup_provider(monkeypatch)

    with pytest.raises(ValueError):
        asyncio.run(
            policy_gateway.generate_with_policy(
                db=Mock(),
                user_id=1,
                repo_id=10,
                files={"node_modules/package/index.js": "private data"},
                instructions="Analyze code",
                config=Mock(ai_provider="openai"),
            )
        )

    provider.generate.assert_not_called()
