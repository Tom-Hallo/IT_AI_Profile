"""Unit tests for GitHub OAuth state and application sessions."""

from unittest.mock import Mock

import pytest

from app.modules.auth import service


@pytest.fixture
def fake_redis(monkeypatch):
    """Thay Redis thật bằng Redis giả lập."""
    redis = Mock()
    monkeypatch.setattr(service, "_get_redis", lambda: redis)
    return redis


def test_create_oauth_state(fake_redis):
    browser_binding = "browser-secret"
    state = service.create_oauth_state(browser_binding)

    assert isinstance(state, str)
    assert len(state) > 20

    fake_redis.set.assert_called_once_with(
        f"{service.OAUTH_STATE_PREFIX}{state}",
        browser_binding,
        ex=service.OAUTH_STATE_TTL_SECONDS,
    )


def test_create_oauth_state_without_binding():
    with pytest.raises(ValueError):
        service.create_oauth_state("")


def test_consume_oauth_state_success(fake_redis):
    fake_redis.getdel.return_value = b"browser-secret"

    result = service.consume_oauth_state(
        "valid-state",
        "browser-secret",
    )

    assert result is True
    fake_redis.getdel.assert_called_once_with(
        f"{service.OAUTH_STATE_PREFIX}valid-state"
    )


def test_consume_oauth_state_wrong_browser(fake_redis):
    fake_redis.getdel.return_value = b"another-browser"

    result = service.consume_oauth_state(
        "valid-state",
        "browser-secret",
    )

    assert result is False


def test_consume_oauth_state_invalid(fake_redis):
    fake_redis.getdel.return_value = None

    result = service.consume_oauth_state(
        "invalid-state",
        "browser-secret",
    )

    assert result is False


def test_consume_oauth_state_empty(fake_redis):
    result = service.consume_oauth_state("", "browser-secret")

    assert result is False
    fake_redis.getdel.assert_not_called()


def test_consume_oauth_state_without_binding(fake_redis):
    result = service.consume_oauth_state("valid-state", "")

    assert result is False
    fake_redis.getdel.assert_not_called()


def test_create_session(fake_redis):
    session_id = service.create_session(123)

    assert isinstance(session_id, str)
    assert len(session_id) > 20

    fake_redis.set.assert_called_once_with(
        f"{service.SESSION_PREFIX}{session_id}",
        "123",
        ex=service.SESSION_TTL_SECONDS,
    )


def test_create_session_invalid_user_id(fake_redis):
    with pytest.raises(ValueError):
        service.create_session(0)

    fake_redis.set.assert_not_called()


def test_get_session_user_id_success(fake_redis):
    fake_redis.get.return_value = b"123"

    result = service.get_session_user_id("valid-session")

    assert result == 123


def test_get_session_user_id_missing(fake_redis):
    fake_redis.get.return_value = None

    result = service.get_session_user_id("missing-session")

    assert result is None


def test_get_session_user_id_invalid_value(fake_redis):
    fake_redis.get.return_value = b"invalid"

    result = service.get_session_user_id("invalid-session")

    assert result is None


def test_get_session_user_id_empty(fake_redis):
    result = service.get_session_user_id(None)

    assert result is None
    fake_redis.get.assert_not_called()


def test_revoke_session_success(fake_redis):
    fake_redis.delete.return_value = 1

    result = service.revoke_session("valid-session")

    assert result is True
    fake_redis.delete.assert_called_once_with(f"{service.SESSION_PREFIX}valid-session")


def test_revoke_session_missing(fake_redis):
    fake_redis.delete.return_value = 0

    result = service.revoke_session("missing-session")

    assert result is False


def test_revoke_session_empty(fake_redis):
    result = service.revoke_session(None)

    assert result is False
    fake_redis.delete.assert_not_called()
