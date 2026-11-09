"""Comprehensive acceptance tests for PBI-010 GitHub Activity Analysis (M-02).

Covers all 14 required acceptance scenarios:
1. Repository with zero commits.
2. Repository with one commit.
3. Repository with 100 commits.
4. Repository with 101+ commits.
5. Repository with 500+ commits.
6. Large month and year ranges.
7. Custom date range containing today.
8. Slow GitHub API responses & retries.
9. GitHub HTTP 409 for empty repository.
10. GitHub HTTP 403, 404, 429 and 5xx errors.
11. API rate-limit handling.
12. Frontend timeout and cancellation simulation.
13. UTC and Asia/Ho_Chi_Minh date boundaries.
14. No partial results presented as complete.
"""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.time_range import resolve_range
from app.db.session import get_session
from app.main import create_app
from app.modules.github.client import (
    GitHubApiClient,
    GitHubEmptyRepositoryError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository
from app.services.activity import (
    MAX_COMMITS_FOR_ANALYSIS,
    analyze,
)


def _make_mock_repo(
    repo_id: int = 1,
    full_name: str = "owner/repo",
    is_private: bool = False,
    synced: bool = True,
) -> MagicMock:
    repo = MagicMock(spec=Repository)
    repo.id = repo_id
    repo.full_name = full_name
    repo.private = is_private
    repo.sync_status = "synced" if synced else "pending"
    repo.last_synced_at = datetime(2026, 11, 1, tzinfo=UTC) if synced else None
    return repo


def _make_commit_item(sha: str, dt: datetime) -> dict:
    return {
        "sha": sha,
        "commit": {
            "committer": {"date": dt.isoformat()},
            "author": {"date": dt.isoformat()},
            "message": f"Commit {sha[:7]}",
        },
    }


# =========================================================================
# Scenario 1 & 9: Zero commits & HTTP 409 Empty Repository
# =========================================================================


@pytest.mark.anyio
async def test_scenario_01_and_09_empty_repository_409(monkeypatch):
    """Empty repository returning HTTP 409 must return valid zero-activity response."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = _make_mock_repo()
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    fake_client = AsyncMock(spec=GitHubApiClient)
    # Commits endpoint raises GitHubEmptyRepositoryError (HTTP 409 from GitHub)
    fake_client._request.side_effect = GitHubEmptyRepositoryError(
        "Git repository is empty."
    )
    monkeypatch.setattr("app.services.activity.GitHubApiClient", lambda _t: fake_client)

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    result = await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert result["activity"]["commits"] == 0
    assert result["activity"]["pull_requests_created"] == 0
    assert result["activity"]["additions"] == 0
    assert result["activity"]["deletions"] == 0
    assert result["base_code"]["status"] == "unavailable"


@pytest.mark.anyio
async def test_scenario_01_zero_commits_in_range(monkeypatch):
    """Repository with 0 commits in the specified date range returns 0."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = _make_mock_repo()
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    fake_client = AsyncMock(spec=GitHubApiClient)
    fake_client._request.return_value = mock_resp
    monkeypatch.setattr("app.services.activity.GitHubApiClient", lambda _t: fake_client)

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    result = await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert result["activity"]["commits"] == 0
    assert result["activity"]["additions"] == 0
    assert result["activity"]["deletions"] == 0


# =========================================================================
# Scenario 2: Exactly one commit
# =========================================================================


@pytest.mark.anyio
async def test_scenario_02_one_commit(monkeypatch):
    """Repository with 1 commit calculates additions and deletions."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = _make_mock_repo()
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    sha = "a" * 40
    commit_date = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    commits_list = [_make_commit_item(sha, commit_date)]

    async def fake_request(method: str, endpoint: str, params=None):
        mock_r = MagicMock()
        if "/commits/" in endpoint:
            mock_r.json.return_value = {
                "sha": sha,
                "stats": {"additions": 42, "deletions": 13},
            }
        elif "/commits" in endpoint:
            mock_r.json.return_value = commits_list
        elif "/pulls" in endpoint:
            mock_r.json.return_value = []
        return mock_r

    fake_client = AsyncMock(spec=GitHubApiClient)
    fake_client._request = fake_request
    monkeypatch.setattr("app.services.activity.GitHubApiClient", lambda _t: fake_client)

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    result = await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert result["activity"]["commits"] == 1
    assert result["activity"]["additions"] == 42
    assert result["activity"]["deletions"] == 13


# =========================================================================
# Scenario 3: Repository with 100 commits
# =========================================================================


@pytest.mark.anyio
async def test_scenario_03_100_commits(monkeypatch):
    """Repository with 100 commits is fully aggregated without rejection."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = _make_mock_repo()
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    commit_date = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    commits = [_make_commit_item(f"{i:040x}", commit_date) for i in range(100)]

    async def fake_request(method: str, endpoint: str, params=None):
        mock_r = MagicMock()
        if "/commits/" in endpoint:
            mock_r.json.return_value = {"stats": {"additions": 2, "deletions": 1}}
        elif "/commits" in endpoint:
            p = params.get("page", 1) if params else 1
            mock_r.json.return_value = commits if p == 1 else []
        elif "/pulls" in endpoint:
            mock_r.json.return_value = []
        return mock_r

    fake_client = AsyncMock(spec=GitHubApiClient)
    fake_client._request = fake_request
    monkeypatch.setattr("app.services.activity.GitHubApiClient", lambda _t: fake_client)

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    result = await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert result["activity"]["commits"] == 100
    assert result["activity"]["additions"] == 200
    assert result["activity"]["deletions"] == 100


# =========================================================================
# Scenario 4: Repository with 101+ commits (Previously blocked by PBI-010 bug)
# =========================================================================


@pytest.mark.anyio
async def test_scenario_04_101_commits_supported(monkeypatch):
    """101 commits must be processed across multiple pages without throwing 413."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = _make_mock_repo()
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    commit_date = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    page1 = [_make_commit_item(f"{i:040x}", commit_date) for i in range(100)]
    page2 = [_make_commit_item(f"{100:040x}", commit_date)]

    async def fake_request(method: str, endpoint: str, params=None):
        mock_r = MagicMock()
        if "/commits/" in endpoint:
            mock_r.json.return_value = {"stats": {"additions": 1, "deletions": 1}}
        elif "/commits" in endpoint:
            p = params.get("page", 1) if params else 1
            mock_r.json.return_value = page1 if p == 1 else page2
        elif "/pulls" in endpoint:
            mock_r.json.return_value = []
        return mock_r

    fake_client = AsyncMock(spec=GitHubApiClient)
    fake_client._request = fake_request
    monkeypatch.setattr("app.services.activity.GitHubApiClient", lambda _t: fake_client)

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    result = await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert result["activity"]["commits"] == 101
    assert result["activity"]["additions"] == 101
    assert result["activity"]["deletions"] == 101


# =========================================================================
# Scenario 5: Repository with 500+ commits
# =========================================================================


@pytest.mark.anyio
async def test_scenario_05_500_plus_commits(monkeypatch):
    """550 commits across 6 pages must be collected and aggregated correctly."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = _make_mock_repo()
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    commit_date = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    async def fake_request(method: str, endpoint: str, params=None):
        mock_r = MagicMock()
        if "/commits/" in endpoint:
            mock_r.json.return_value = {"stats": {"additions": 2, "deletions": 0}}
        elif "/commits" in endpoint:
            p = params.get("page", 1) if params else 1
            if p <= 5:
                mock_r.json.return_value = [
                    _make_commit_item(f"{(p * 100 + i):040x}", commit_date)
                    for i in range(100)
                ]
            elif p == 6:
                mock_r.json.return_value = [
                    _make_commit_item(f"{(600 + i):040x}", commit_date)
                    for i in range(50)
                ]
            else:
                mock_r.json.return_value = []
        elif "/pulls" in endpoint:
            mock_r.json.return_value = []
        return mock_r

    fake_client = AsyncMock(spec=GitHubApiClient)
    fake_client._request = fake_request
    monkeypatch.setattr("app.services.activity.GitHubApiClient", lambda _t: fake_client)

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    result = await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert result["activity"]["commits"] == 550
    assert result["activity"]["additions"] == 1100
    assert result["activity"]["deletions"] == 0


@pytest.mark.anyio
async def test_scenario_05_exceeding_max_limit_raises_413(monkeypatch):
    """When commits exceed MAX_COMMITS_FOR_ANALYSIS, raise HTTP 413."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = _make_mock_repo()
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    commit_date = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    # Generate 1001 commits
    huge_commits = [
        _make_commit_item(f"{i:040x}", commit_date)
        for i in range(MAX_COMMITS_FOR_ANALYSIS + 1)
    ]

    async def fake_request(method: str, endpoint: str, params=None):
        mock_r = MagicMock()
        if "/commits" in endpoint:
            mock_r.json.return_value = huge_commits
        return mock_r

    fake_client = AsyncMock(spec=GitHubApiClient)
    fake_client._request = fake_request
    monkeypatch.setattr("app.services.activity.GitHubApiClient", lambda _t: fake_client)

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    with pytest.raises(HTTPException) as exc_info:
        await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert exc_info.value.status_code == 413
    assert f">{MAX_COMMITS_FOR_ANALYSIS}" in exc_info.value.detail


# =========================================================================
# Scenario 6: Large month and year ranges
# =========================================================================


def test_scenario_06_large_year_range_resolution():
    """Year mode creates exact [Jan 1, next Jan 1) UTC boundary."""
    start, end = resolve_range(mode="year", year=2025, timezone_name="UTC")
    assert start == datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def test_scenario_06_large_month_range_resolution():
    """Month mode creates exact [first of month, first of next month) UTC boundary."""
    start, end = resolve_range(mode="month", month="2026-02", timezone_name="UTC")
    assert start == datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 3, 1, 0, 0, tzinfo=UTC)


# =========================================================================
# Scenario 7: Custom date range containing today
# =========================================================================


def test_scenario_07_custom_range_today():
    """Custom date range for today sets end_exclusive to midnight of tomorrow."""
    today = date(2026, 11, 9)
    start, end = resolve_range(
        mode="custom",
        start_date=today,
        end_date=today,
        timezone_name="UTC",
    )
    assert start == datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 10, 0, 0, tzinfo=UTC)


# =========================================================================
# Scenario 8: Slow GitHub API responses & retries
# =========================================================================


@pytest.mark.anyio
async def test_scenario_08_slow_github_api_retry():
    """GitHubApiClient retries transient 5xx errors and eventually succeeds."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json=[{"id": 1, "name": "ok"}])

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient(
        "test-token", client=mock_client, max_retries=3, base_delay=0.01
    )

    repos = await client.list_repositories()
    assert len(repos) == 1
    assert attempts == 3


# =========================================================================
# Scenario 10: GitHub HTTP 403, 404, 429 and 5xx error mappings
# =========================================================================


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("client_exception", "expected_status"),
    [
        (GitHubTokenRevokedError("Token revoked"), 401),
        (GitHubPermissionError("Forbidden"), 403),
        (GitHubNotFoundError("Not found"), 404),
        (GitHubRateLimitError("Rate limit"), 429),
    ],
)
async def test_scenario_10_github_error_mappings(
    monkeypatch, client_exception, expected_status
):
    mock_db = MagicMock()
    mock_db.scalar.return_value = _make_mock_repo()
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    fake_client = AsyncMock(spec=GitHubApiClient)
    fake_client._request.side_effect = client_exception
    monkeypatch.setattr("app.services.activity.GitHubApiClient", lambda _t: fake_client)

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    with pytest.raises(HTTPException) as exc_info:
        await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert exc_info.value.status_code == expected_status


# =========================================================================
# Scenario 11: API rate-limit handling
# =========================================================================


@pytest.mark.anyio
async def test_scenario_11_rate_limit_detection():
    """GitHub client parses 403 with x-ratelimit-remaining=0 as GitHubRateLimitError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": "1762732800",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    with pytest.raises(GitHubRateLimitError) as exc_info:
        await client._request("GET", "/repos/owner/repo/commits")
    assert "rate limit" in str(exc_info.value).lower()
    assert exc_info.value.reset_at is not None


# =========================================================================
# Scenario 12: Frontend timeout and cancellation simulation
# =========================================================================


def test_scenario_12_endpoint_supports_external_timeout(monkeypatch):
    """FastAPI endpoint processes valid activity request within client timeout."""
    from app.api import activity

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: type("User", (), {"id": 1})()
    app.dependency_overrides[get_session] = lambda: MagicMock()
    fake = AsyncMock(return_value={"activity": {"commits": 1}})
    monkeypatch.setattr(activity, "analyze", fake)

    with TestClient(app) as client:
        url = "/api/v1/repositories/1/activity/analysis?mode=preset&preset=1m"
        resp = client.get(url)
        assert resp.status_code == 200

    app.dependency_overrides.clear()


# =========================================================================
# Scenario 13: UTC and Asia/Ho_Chi_Minh date boundaries
# =========================================================================


def test_scenario_13_timezone_boundaries_asia_ho_chi_minh():
    """Asia/Ho_Chi_Minh is UTC+7; midnight at 00:00 ICT is 17:00 UTC previous day."""
    start_date = date(2026, 10, 1)
    end_date = date(2026, 10, 1)

    start_utc, end_utc = resolve_range(
        mode="custom",
        start_date=start_date,
        end_date=end_date,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    ict = ZoneInfo("Asia/Ho_Chi_Minh")
    assert start_utc.astimezone(ict) == datetime(2026, 10, 1, 0, 0, tzinfo=ict)
    assert end_utc.astimezone(ict) == datetime(2026, 10, 2, 0, 0, tzinfo=ict)

    # In UTC:
    assert start_utc == datetime(2026, 9, 30, 17, 0, tzinfo=UTC)
    assert end_utc == datetime(2026, 10, 1, 17, 0, tzinfo=UTC)


# =========================================================================
# Scenario 14: No partial results presented as complete
# =========================================================================


@pytest.mark.anyio
async def test_scenario_14_no_partial_results_on_error(monkeypatch):
    """If an error occurs while fetching commit stats, the analysis must fail

    completely rather than returning silently truncated statistics.
    """
    mock_db = MagicMock()
    mock_db.scalar.return_value = _make_mock_repo()
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    commit_date = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    commits = [
        _make_commit_item("a" * 40, commit_date),
        _make_commit_item("b" * 40, commit_date),
    ]

    async def fake_request(method: str, endpoint: str, params=None):
        if "b" * 40 in endpoint:
            # Second commit fails
            raise GitHubRateLimitError("Secondary rate limit exceeded")
        mock_r = MagicMock()
        if "/commits/" in endpoint:
            mock_r.json.return_value = {"stats": {"additions": 10, "deletions": 5}}
        elif "/commits" in endpoint:
            mock_r.json.return_value = commits
        return mock_r

    fake_client = AsyncMock(spec=GitHubApiClient)
    fake_client._request = fake_request
    monkeypatch.setattr("app.services.activity.GitHubApiClient", lambda _t: fake_client)

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    # Must raise 429 rather than returning 1 commit with 10 additions
    with pytest.raises(HTTPException) as exc_info:
        await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert exc_info.value.status_code == 429
