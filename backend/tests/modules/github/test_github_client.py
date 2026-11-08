"""Tests for GitHub REST API client (pagination, rate limits, retry)."""

from datetime import UTC, datetime

import httpx
import pytest

from app.modules.github.client import (
    GitHubApiClient,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubServerError,
    GitHubTokenRevokedError,
    _parse_next_link,
)


def test_parse_next_link():
    link_header = (
        '<https://api.github.com/user/repos?page=2&per_page=100>; rel="next", '
        '<https://api.github.com/user/repos?page=5&per_page=100>; rel="last"'
    )
    assert _parse_next_link(link_header) == "https://api.github.com/user/repos?page=2&per_page=100"

    no_next = '<https://api.github.com/user/repos?page=5&per_page=100>; rel="last"'
    assert _parse_next_link(no_next) is None
    assert _parse_next_link(None) is None


@pytest.mark.anyio
async def test_list_repositories_single_page():
    fake_repos = [
        {"id": 101, "name": "repo-one", "full_name": "user/repo-one"},
        {"id": 102, "name": "repo-two", "full_name": "user/repo-two"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fake_repos)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, base_delay=0.01)

    repos = await client.list_repositories()
    assert len(repos) == 2
    assert repos[0]["id"] == 101
    assert repos[1]["name"] == "repo-two"


@pytest.mark.anyio
async def test_list_repositories_multi_page():
    page1_repos = [{"id": 101, "name": "repo-one"}]
    page2_repos = [{"id": 102, "name": "repo-two"}]

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(200, json=page2_repos)
        return httpx.Response(
            200,
            json=page1_repos,
            headers={"link": '<https://api.github.com/user/repos?page=2>; rel="next"'},
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, base_delay=0.01)

    repos = await client.list_repositories()
    assert len(repos) == 2
    assert repos[0]["id"] == 101
    assert repos[1]["id"] == 102


@pytest.mark.anyio
async def test_get_repository_languages():
    lang_data = {"Python": 185000, "TypeScript": 92000, "HTML": 18000}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=lang_data)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, base_delay=0.01)

    langs = await client.get_repository_languages("user", "repo-one")
    assert langs == {"Python": 185000, "TypeScript": 92000, "HTML": 18000}


@pytest.mark.anyio
async def test_token_revoked_raises_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, base_delay=0.01)

    with pytest.raises(GitHubTokenRevokedError, match="không hợp lệ hoặc đã bị thu hồi"):
        await client.list_repositories()


@pytest.mark.anyio
async def test_rate_limit_raises_error_with_reset_header():
    reset_time = int(datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset_time)},
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, base_delay=0.01)

    with pytest.raises(GitHubRateLimitError) as exc_info:
        await client.list_repositories()

    assert exc_info.value.reset_at is not None
    assert exc_info.value.reset_at.timestamp() == reset_time


@pytest.mark.anyio
async def test_rate_limit_429():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"message": "Too Many Requests"},
            headers={"retry-after": "60"},
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, base_delay=0.01)

    with pytest.raises(GitHubRateLimitError) as exc_info:
        await client.list_repositories()

    assert exc_info.value.retry_after == 60


@pytest.mark.anyio
async def test_permission_error_403_not_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "Resource not accessible by integration"},
            headers={"x-ratelimit-remaining": "60"},
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, base_delay=0.01)

    with pytest.raises(GitHubPermissionError, match="Không có quyền truy cập"):
        await client.list_repositories()


@pytest.mark.anyio
async def test_not_found_error_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, base_delay=0.01)

    with pytest.raises(GitHubNotFoundError):
        await client.get_repository_details("user", "missing-repo")


@pytest.mark.anyio
async def test_transient_500_retries_and_succeeds():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(502, text="Bad Gateway")
        return httpx.Response(200, json=[{"id": 1, "name": "ok"}])

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, max_retries=2, base_delay=0.01)

    repos = await client.list_repositories()
    assert len(repos) == 1
    assert attempts == 2


@pytest.mark.anyio
async def test_server_error_exhausts_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client, max_retries=1, base_delay=0.01)

    with pytest.raises(GitHubServerError, match="lỗi máy chủ"):
        await client.list_repositories()


@pytest.mark.anyio
async def test_invalid_token_constructor():
    with pytest.raises(ValueError, match="access_token không được để trống"):
        GitHubApiClient("")
