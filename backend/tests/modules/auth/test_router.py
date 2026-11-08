
"""Tests for GitHub OAuth authentication routes."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.modules.auth import router as auth_router
from app.api import dependencies as api_dependencies

@pytest.fixture
def client(monkeypatch):
    """Tạo test app riêng cho Auth router."""

    fake_settings = SimpleNamespace(
    app_env="test",
    frontend_url="http://localhost:5173",
    cors_origins=["http://localhost:5173"],
    github_oauth_enabled=True,
    github_client_id="test-client-id",
    github_redirect_uri=(
        "http://localhost:8000/api/v1/auth/github/callback"
    ),
)

    monkeypatch.setattr(auth_router, "settings", fake_settings)

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1")
    app.dependency_overrides[get_session] = lambda: object()

    return TestClient(app)


def set_oauth_cookies(client, state="valid-state"):
    """Thiết lập cookie OAuth giả lập."""

    client.cookies.set(
        auth_router.OAUTH_STATE_COOKIE,
        state,
        path="/api/v1/auth",
    )
    client.cookies.set(
        auth_router.OAUTH_BROWSER_COOKIE,
        "browser-binding",
        path="/api/v1/auth",
    )


def test_github_login_redirects_to_github(client, monkeypatch):
    """Kiểm tra chuyển hướng sang GitHub."""

    monkeypatch.setattr(
        auth_router,
        "create_oauth_state",
        lambda binding: "generated-state",
    )

    response = client.get(
        "/api/v1/auth/github",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "https://github.com/login/oauth/authorize?"
    )
    assert "state=generated-state" in response.headers["location"]
    assert auth_router.OAUTH_STATE_COOKIE in response.headers["set-cookie"]
    assert auth_router.OAUTH_BROWSER_COOKIE in response.headers["set-cookie"]


def test_github_callback_success(client, monkeypatch):
    """Kiểm tra callback thành công và tạo session."""

    set_oauth_cookies(client)

    monkeypatch.setattr(
        auth_router,
        "consume_oauth_state",
        lambda state, binding: True,
    )

    async def fake_get_identity(code):
        return SimpleNamespace(
            provider_user_id="12345",
            email="test@example.com",
            full_name="Test User",
        )

    monkeypatch.setattr(
        auth_router,
        "get_github_identity",
        fake_get_identity,
    )

    monkeypatch.setattr(
        auth_router,
        "get_or_create_github_user",
        lambda db, identity: SimpleNamespace(id=10),
    )

    monkeypatch.setattr(
        auth_router,
        "create_session",
        lambda user_id: "fake-session-id",
    )

    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "fake-code", "state": "valid-state"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/"
    assert auth_router.SESSION_COOKIE in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_github_callback_invalid_state(client, monkeypatch):
    """Từ chối callback có state không khớp cookie."""

    set_oauth_cookies(client, state="different-state")

    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "fake-code", "state": "valid-state"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "auth_error=oauth_state_invalid" in response.headers["location"]


def test_github_callback_expired_state(client, monkeypatch):
    """Từ chối callback khi state không còn trong Redis."""

    set_oauth_cookies(client)

    monkeypatch.setattr(
        auth_router,
        "consume_oauth_state",
        lambda state, binding: False,
    )

    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "fake-code", "state": "valid-state"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "auth_error=oauth_state_invalid" in response.headers["location"]


def test_github_callback_access_denied(client, monkeypatch):
    """Xử lý trường hợp người dùng từ chối cấp quyền."""

    set_oauth_cookies(client)

    monkeypatch.setattr(
        auth_router,
        "consume_oauth_state",
        lambda state, binding: True,
    )

    response = client.get(
        "/api/v1/auth/github/callback",
        params={
            "state": "valid-state",
            "error": "access_denied",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "auth_error=github_access_denied" in response.headers["location"]


def test_github_callback_without_code(client, monkeypatch):
    """Xử lý callback không có authorization code."""

    set_oauth_cookies(client)

    monkeypatch.setattr(
        auth_router,
        "consume_oauth_state",
        lambda state, binding: True,
    )

    response = client.get(
        "/api/v1/auth/github/callback",
        params={"state": "valid-state"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "auth_error=github_login_failed" in response.headers["location"]


def test_github_callback_account_conflict(client, monkeypatch):
    """Xử lý tài khoản GitHub có email trùng tài khoản hiện tại."""

    set_oauth_cookies(client)

    monkeypatch.setattr(
        auth_router,
        "consume_oauth_state",
        lambda state, binding: True,
    )

    async def fake_get_identity(code):
        return SimpleNamespace(
            provider_user_id="12345",
            email="existing@example.com",
            full_name="Test User",
        )

    def fake_get_or_create(db, identity):
        raise auth_router.GitHubAccountConflictError()

    monkeypatch.setattr(
        auth_router,
        "get_github_identity",
        fake_get_identity,
    )
    monkeypatch.setattr(
        auth_router,
        "get_or_create_github_user",
        fake_get_or_create,
    )

    response = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "fake-code", "state": "valid-state"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "auth_error=github_account_conflict" in response.headers["location"]


def test_auth_me_without_session_returns_401(client, monkeypatch):
    """Người chưa đăng nhập không được truy cập thông tin cá nhân."""

    monkeypatch.setattr(
        api_dependencies,
        "get_session_user_id",
        lambda session_id: None,
    )

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_auth_me_expired_session_returns_401(client, monkeypatch):
    """Session hết hạn không được truy cập thông tin cá nhân."""

    monkeypatch.setattr(
        api_dependencies,
        "get_session_user_id",
        lambda session_id: None,
    )

    client.cookies.set(
        auth_router.SESSION_COOKIE,
        "expired-session",
        path="/",
    )

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_auth_me_success_does_not_expose_password(client, monkeypatch):
    """Người đăng nhập hợp lệ chỉ nhận thông tin an toàn."""

    fake_user = SimpleNamespace(
        id=10,
        email="test@example.com",
        full_name="Test User",
        hashed_password="secret-hash",
    )

    fake_db = SimpleNamespace(
        scalar=lambda statement: fake_user,
    )

    client.app.dependency_overrides[get_session] = lambda: fake_db

    monkeypatch.setattr(
        api_dependencies,
        "get_session_user_id",
        lambda session_id: 10,
    )

    client.cookies.set(
        auth_router.SESSION_COOKIE,
        "valid-session",
        path="/",
    )

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": 10,
        "email": "test@example.com",
        "full_name": "Test User",
    }
    assert "hashed_password" not in response.json()

def test_auth_logout_success(client, monkeypatch):
    """Đăng xuất thành công và xóa session cookie."""

    revoked_sessions = []

    def fake_revoke_session(session_id):
        revoked_sessions.append(session_id)
        return True

    monkeypatch.setattr(
        auth_router,
        "revoke_session",
        fake_revoke_session,
    )

    client.cookies.set(
        auth_router.SESSION_COOKIE,
        "valid-session",
        path="/",
    )

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 204
    assert revoked_sessions == ["valid-session"]
    assert auth_router.SESSION_COOKIE in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_auth_logout_invalid_origin_returns_403(client, monkeypatch):
    """Không cho phép logout từ Origin không hợp lệ."""

    monkeypatch.setattr(
        auth_router,
        "revoke_session",
        lambda session_id: True,
    )

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://malicious.example"},
    )

    assert response.status_code == 403


def test_auth_logout_redis_error_returns_503(client, monkeypatch):
    """Trả lỗi 503 khi Redis không thể thu hồi session."""

    def fake_revoke_session(session_id):
        raise auth_router.RedisError("Redis unavailable")

    monkeypatch.setattr(
        auth_router,
        "revoke_session",
        fake_revoke_session,
    )

    client.cookies.set(
        auth_router.SESSION_COOKIE,
        "valid-session",
        path="/",
    )

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 503
        