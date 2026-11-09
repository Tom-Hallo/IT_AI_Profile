"""Tests for GitHub OAuth provider integration."""

import asyncio
from types import SimpleNamespace

import pytest

from app.modules.auth import github


class FakeResponse:
    """Giả lập HTTP response từ GitHub."""

    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class FakeAsyncClient:
    """Giả lập HTTP client, không gọi mạng thật."""

    def __init__(self, responses, **kwargs):
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def post(self, url, **kwargs):
        return self.responses[url]

    async def get(self, url, **kwargs):
        return self.responses[url]


def setup_github_mock(monkeypatch, responses):
    """Cấu hình GitHub giả lập cho từng bài test."""

    fake_settings = SimpleNamespace(
        github_oauth_enabled=True,
        github_client_id="test-client-id",
        github_client_secret=SimpleNamespace(
            get_secret_value=lambda: "test-client-secret"
        ),
        github_redirect_uri=("http://localhost:8000/api/v1/auth/github/callback"),
    )

    monkeypatch.setattr(github, "settings", fake_settings)

    monkeypatch.setattr(
        github.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(responses, **kwargs),
    )


def test_get_github_identity_success(monkeypatch):
    """Lấy danh tính GitHub thành công."""

    responses = {
        github.GITHUB_TOKEN_URL: FakeResponse({"access_token": "fake-access-token"}),
        github.GITHUB_USER_URL: FakeResponse(
            {
                "id": 12345,
                "login": "test-user",
                "name": "Test User",
            }
        ),
        github.GITHUB_EMAILS_URL: FakeResponse(
            [
                {
                    "email": "TEST@example.com",
                    "primary": True,
                    "verified": True,
                },
                {
                    "email": "other@example.com",
                    "primary": False,
                    "verified": False,
                },
            ]
        ),
    }

    setup_github_mock(monkeypatch, responses)

    identity = asyncio.run(github.get_github_identity("fake-code"))

    assert identity.provider_user_id == "12345"
    assert identity.email == "test@example.com"
    assert identity.full_name == "Test User"


def test_get_github_identity_without_verified_email(monkeypatch):
    """Từ chối tài khoản không có email đã xác minh."""

    responses = {
        github.GITHUB_TOKEN_URL: FakeResponse({"access_token": "fake-access-token"}),
        github.GITHUB_USER_URL: FakeResponse(
            {
                "id": 12345,
                "login": "test-user",
                "name": "Test User",
            }
        ),
        github.GITHUB_EMAILS_URL: FakeResponse(
            [
                {
                    "email": "test@example.com",
                    "primary": True,
                    "verified": False,
                }
            ]
        ),
    }

    setup_github_mock(monkeypatch, responses)

    with pytest.raises(github.GitHubOAuthError):
        asyncio.run(github.get_github_identity("fake-code"))


def test_get_github_identity_without_access_token(monkeypatch):
    """Từ chối khi GitHub không cấp access token."""

    responses = {
        github.GITHUB_TOKEN_URL: FakeResponse({"error": "bad_verification_code"}),
    }

    setup_github_mock(monkeypatch, responses)

    with pytest.raises(github.GitHubOAuthError):
        asyncio.run(github.get_github_identity("invalid-code"))
