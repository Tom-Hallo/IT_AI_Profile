"""Tests for GitHub REST API client (pagination, rate limits, retry)."""

from datetime import UTC, datetime

import httpx
import pytest

from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
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
    assert (
        _parse_next_link(link_header)
        == "https://api.github.com/user/repos?page=2&per_page=100"
    )

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

    with pytest.raises(
        GitHubTokenRevokedError, match="không hợp lệ hoặc đã bị thu hồi"
    ):
        await client.list_repositories()


@pytest.mark.anyio
async def test_rate_limit_raises_error_with_reset_header():
    reset_time = int(datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": str(reset_time),
            },
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
    client = GitHubApiClient(
        "test-token", client=mock_client, max_retries=2, base_delay=0.01
    )

    repos = await client.list_repositories()
    assert len(repos) == 1
    assert attempts == 2


@pytest.mark.anyio
async def test_server_error_exhausts_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient(
        "test-token", client=mock_client, max_retries=1, base_delay=0.01
    )

    with pytest.raises(GitHubServerError, match="lỗi máy chủ"):
        await client.list_repositories()


@pytest.mark.anyio
async def test_invalid_token_constructor():
    with pytest.raises(ValueError, match="access_token không được để trống"):
        GitHubApiClient("")


# ============================================================
# SECURITY TESTS - GITHUB OAUTH TOKEN PROTECTION
# ============================================================


@pytest.mark.anyio
@pytest.mark.parametrize(
    "malicious_url",
    [
        "https://attacker.example.com/steal-token",
        "http://api.github.com/user/repos?page=2",
        "https://api.github.com.attacker.example.com/user/repos",
        "https://attacker.example.com@api.github.com.evil.com/user/repos",
    ],
)
async def test_reject_malicious_pagination_urls(malicious_url):
    """
    GitHub Link header không được phép chuyển OAuth token
    sang domain bên ngoài GitHub API.
    """

    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))

        return httpx.Response(
            200,
            json=[{"id": 101, "name": "repo-one"}],
            headers={"link": f'<{malicious_url}>; rel="next"'},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = GitHubApiClient(
            access_token="test-secret-token",
            client=mock_client,
        )

        with pytest.raises(GitHubApiError):
            await client.list_repositories()

    # Chỉ request trang đầu tiên được thực hiện.
    assert len(requested_urls) == 1

    # Không có request nào gửi đến domain độc hại.
    assert requested_urls[0].startswith("https://api.github.com/")


@pytest.mark.anyio
async def test_reject_direct_request_to_external_domain():
    """
    Không cho phép gọi _request() đến URL bên ngoài GitHub.
    """

    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)

        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = GitHubApiClient(
            access_token="test-secret-token",
            client=mock_client,
        )

        with pytest.raises(GitHubApiError):
            await client._request(
                "GET",
                "https://attacker.example.com/steal-token",
            )

    # URL phải bị từ chối trước khi gửi HTTP request.
    assert len(captured_requests) == 0


@pytest.mark.anyio
async def test_valid_github_pagination_preserves_authorization():
    """
    Phân trang hợp lệ trên api.github.com vẫn hoạt động.
    """

    requested_pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_pages.append(request)

        assert request.url.host == "api.github.com"
        assert request.headers["Authorization"] == "Bearer test-secret-token"

        if request.url.params.get("page") == "2":
            return httpx.Response(
                200,
                json=[{"id": 102, "name": "repo-two"}],
            )

        return httpx.Response(
            200,
            json=[{"id": 101, "name": "repo-one"}],
            headers={
                "link": ('<https://api.github.com/user/repos?page=2>; rel="next"')
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_client:
        client = GitHubApiClient(
            access_token="test-secret-token",
            client=mock_client,
        )

        repositories = await client.list_repositories()

    assert len(repositories) == 2
    assert len(requested_pages) == 2

    assert repositories[0]["id"] == 101
    assert repositories[1]["id"] == 102


@pytest.mark.anyio
async def test_redirect_does_not_forward_github_token():
    """
    GitHub API không được chuyển tiếp OAuth token
    đến URL bên ngoài thông qua HTTP redirect.
    """

    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)

        if request.url.host == "api.github.com":
            return httpx.Response(
                302,
                headers={"location": ("https://attacker.example.com/steal-token")},
            )

        pytest.fail("OAuth request was redirected to an external host!")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as mock_client:
        client = GitHubApiClient(
            access_token="test-secret-token",
            client=mock_client,
        )

        with pytest.raises(GitHubApiError):
            await client.list_repositories()

    assert len(captured_requests) == 1
    assert captured_requests[0].url.host == "api.github.com"
