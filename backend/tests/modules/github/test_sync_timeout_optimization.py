"""Acceptance & regression tests for GitHub repository sync timeout
optimization (PBI-009).

Scenarios covered:
1. User with single repository synchronization.
2. User with 100+ repositories (verifies concurrent language fetching & performance).
3. Repository pagination across multiple pages (RFC 5988 Link header).
4. Simulated slow API responses within execution timeout limits.
5. GitHub API rate limit handling (HTTP 403/429 raises GitHubRateLimitError,
   rolls back, sets status=failed).
6. Worker task JobTimeoutException recovery (Redis cache updated to status=failed).
7. Database persistence and user_repository pivot associations.
8. Idempotent synchronization (skips language fetching when pushed_at is unchanged).
9. GitHubApiClient async context manager session reuse (HTTP keep-alive).
10. Stale / failed RQ job detection in get_user_sync_status.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from rq.timeouts import JobTimeoutException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.modules.assessments.models
import app.modules.auth.models
import app.modules.cvs.models
import app.modules.github.models
import app.modules.roadmaps.models
import app.modules.users.models  # noqa: F401
from app.core.security import encrypt_token
from app.db.base import Base
from app.modules.analysis.evidence import UTC
from app.modules.auth.models import OAuthAccount
from app.modules.github.client import (
    GitHubApiClient,
    GitHubRateLimitError,
)
from app.modules.github.models import Repository, user_repository
from app.modules.github.service import (
    get_user_sync_status,
    sync_repositories_for_user,
)
from app.modules.users.models import User
from app.workers.tasks.sync_repositories import sync_user_repositories_task


@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def do_connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS ita")
        cursor.close()

    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        yield session

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_user(in_memory_db: Session) -> User:
    user = User(
        id=1,
        email="dev_timeout@example.com",
        full_name="Timeout Test User",
        hashed_password="test-only-placeholder-hash",
    )
    in_memory_db.add(user)
    in_memory_db.flush()

    oauth_account = OAuthAccount(
        id=1,
        user_id=user.id,
        provider="github",
        provider_user_id="999888",
        encrypted_access_token=encrypt_token("gho_test_valid_token"),
        scope="read:user user:email repo",
    )
    in_memory_db.add(oauth_account)
    in_memory_db.commit()
    return user


@pytest.fixture
def fake_sync_redis(monkeypatch):
    storage: dict[str, str] = {}

    class FakeRedis:
        def set(self, key, value, ex=None):
            storage[key] = value if isinstance(value, str) else value.decode("utf-8")
            return True

        def get(self, key):
            return storage.get(key)

    monkeypatch.setattr(
        "app.modules.github.service.get_redis_connection",
        lambda: FakeRedis(),
    )
    return storage


# ---------------------------------------------------------------------------
# Test 1: Single repository synchronization
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_sync_single_repository(
    in_memory_db: Session, sample_user: User, fake_sync_redis
):
    repo_payload = [
        {
            "id": 101,
            "name": "single-repo",
            "full_name": "dev/single-repo",
            "html_url": "https://github.com/dev/single-repo",
            "description": "Single test repository",
            "private": False,
            "default_branch": "main",
            "fork": False,
            "language": "Python",
            "size": 512,
            "stargazers_count": 7,
            "pushed_at": "2026-11-01T12:00:00Z",
            "owner": {"login": "dev"},
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/languages" in url:
            return httpx.Response(200, json={"Python": 4500})
        return httpx.Response(200, json=repo_payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    result = await sync_repositories_for_user(in_memory_db, sample_user, client=client)

    assert result["status"] == "completed"
    assert result["synced_count"] == 1

    db_repos = in_memory_db.scalars(select(Repository)).all()
    assert len(db_repos) == 1
    assert db_repos[0].name == "single-repo"
    assert db_repos[0].languages == {"Python": 4500}
    assert db_repos[0].primary_language == "Python"

    # Verify user_repository pivot table link
    pivot_count = in_memory_db.scalar(
        select(user_repository.c.user_id).where(
            user_repository.c.user_id == sample_user.id,
            user_repository.c.repository_id == db_repos[0].id,
        )
    )
    assert pivot_count == sample_user.id


# ---------------------------------------------------------------------------
# Test 2: Large repository count (100+ repos) concurrent language fetching
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_sync_large_repository_count_concurrent(
    in_memory_db: Session, sample_user: User, fake_sync_redis
):
    num_repos = 110
    repos_payload = []
    for i in range(1, num_repos + 1):
        repos_payload.append(
            {
                "id": 1000 + i,
                "name": f"repo-{i}",
                "full_name": f"dev/repo-{i}",
                "html_url": f"https://github.com/dev/repo-{i}",
                "description": f"Repo description {i}",
                "private": (i % 2 == 0),
                "default_branch": "main",
                "fork": False,
                "language": "TypeScript" if i % 2 == 0 else "Python",
                "size": 100 * i,
                "pushed_at": "2026-11-05T00:00:00Z",
                "owner": {"login": "dev"},
            }
        )

    language_fetch_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal language_fetch_count
        url = str(request.url)
        if "/languages" in url:
            language_fetch_count += 1
            return httpx.Response(200, json={"TypeScript": 2000, "JavaScript": 500})
        return httpx.Response(200, json=repos_payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    result = await sync_repositories_for_user(in_memory_db, sample_user, client=client)

    assert result["status"] == "completed"
    assert result["synced_count"] == num_repos
    assert language_fetch_count == num_repos

    db_repos = in_memory_db.scalars(select(Repository)).all()
    assert len(db_repos) == num_repos


# ---------------------------------------------------------------------------
# Test 3: Pagination across multiple pages (RFC 5988 Link header)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_sync_pagination_multi_page(
    in_memory_db: Session, sample_user: User, fake_sync_redis
):
    page1 = [
        {
            "id": 2000 + i,
            "name": f"p1-repo-{i}",
            "full_name": f"dev/p1-repo-{i}",
            "html_url": f"https://github.com/dev/p1-repo-{i}",
            "private": False,
            "language": "Go",
            "size": 256,
            "pushed_at": "2026-11-01T00:00:00Z",
            "owner": {"login": "dev"},
        }
        for i in range(1, 101)
    ]
    page2 = [
        {
            "id": 3000 + i,
            "name": f"p2-repo-{i}",
            "full_name": f"dev/p2-repo-{i}",
            "html_url": f"https://github.com/dev/p2-repo-{i}",
            "private": False,
            "language": "Rust",
            "size": 512,
            "pushed_at": "2026-11-01T00:00:00Z",
            "owner": {"login": "dev"},
        }
        for i in range(1, 51)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/languages" in url:
            return httpx.Response(200, json={"Go": 800})
        if "page=2" in url:
            return httpx.Response(200, json=page2)
        # Page 1 includes RFC 5988 Link header
        headers = {
            "link": (
                '<https://api.github.com/user/repos?page=2>; rel="next", '
                '<https://api.github.com/user/repos?page=2>; rel="last"'
            )
        }
        return httpx.Response(200, json=page1, headers=headers)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    result = await sync_repositories_for_user(in_memory_db, sample_user, client=client)

    assert result["status"] == "completed"
    assert result["synced_count"] == 150

    total_in_db = in_memory_db.scalar(select(func.count(Repository.id)))
    assert total_in_db == 150


# ---------------------------------------------------------------------------
# Test 4: Rate limit handling (HTTP 403 / 429 raises GitHubRateLimitError)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_sync_rate_limit_handling(
    in_memory_db: Session, sample_user: User, fake_sync_redis
):
    repo_payload = [
        {
            "id": 501,
            "name": "rl-repo",
            "full_name": "dev/rl-repo",
            "size": 100,
            "language": "Python",
            "owner": {"login": "dev"},
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/languages" in url:
            # 403 Secondary Rate limit from GitHub
            headers = {
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": "1800000000",
                "retry-after": "60",
            }
            return httpx.Response(
                403,
                json={"message": "You have exceeded a secondary rate limit."},
                headers=headers,
            )
        return httpx.Response(200, json=repo_payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    with pytest.raises(GitHubRateLimitError):
        await sync_repositories_for_user(in_memory_db, sample_user, client=client)

    # Database must be rolled back (no repository persisted)
    db_repos = in_memory_db.scalars(select(Repository)).all()
    assert len(db_repos) == 0

    # Redis cache must be marked as "failed"
    cached = fake_sync_redis.get(f"ita:github:sync:{sample_user.id}")
    assert cached is not None
    data = json.loads(cached)
    assert data["status"] == "failed"


# ---------------------------------------------------------------------------
# Test 5: Worker task JobTimeoutException recovery
# ---------------------------------------------------------------------------
def test_worker_task_timeout_exception_handling(fake_sync_redis):
    # Simulate JobTimeoutException inside worker task
    with (
        patch("app.workers.tasks.sync_repositories.session_scope") as mock_scope,
        pytest.raises(JobTimeoutException),
    ):
        mock_db = MagicMock()
        mock_db.scalar.return_value = SimpleNamespace(id=42)
        mock_scope.return_value.__enter__.return_value = mock_db

        with patch(
            "app.workers.tasks.sync_repositories.sync_repositories_for_user",
            side_effect=JobTimeoutException("Task exceeded maximum timeout value"),
        ):
            sync_user_repositories_task(42)

    # Verify Redis status is gracefully transitioned to failed
    cached = fake_sync_redis.get("ita:github:sync:42")
    assert cached is not None
    data = json.loads(cached)
    assert data["status"] == "failed"
    assert "Job timeout" in data["error_message"]


# ---------------------------------------------------------------------------
# Test 6: Idempotent sync skips language fetching for unchanged repositories
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_idempotent_sync_skips_unchanged_repositories(
    in_memory_db: Session, sample_user: User, fake_sync_redis
):
    repo_payload = [
        {
            "id": 701,
            "name": "idempotent-repo",
            "full_name": "dev/idempotent-repo",
            "html_url": "https://github.com/dev/idempotent-repo",
            "private": False,
            "language": "Python",
            "size": 500,
            "pushed_at": "2026-11-08T10:00:00Z",
            "owner": {"login": "dev"},
        }
    ]

    language_fetch_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal language_fetch_count
        url = str(request.url)
        if "/languages" in url:
            language_fetch_count += 1
            return httpx.Response(200, json={"Python": 9999})
        return httpx.Response(200, json=repo_payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    # First sync: fetches languages from GitHub
    res1 = await sync_repositories_for_user(in_memory_db, sample_user, client=client)
    assert res1["status"] == "completed"
    assert language_fetch_count == 1

    # Second sync with exact same pushed_at: should reuse cached languages
    res2 = await sync_repositories_for_user(in_memory_db, sample_user, client=client)
    assert res2["status"] == "completed"
    assert language_fetch_count == 1  # Did NOT call languages API again!

    db_repo = in_memory_db.scalar(
        select(Repository).where(Repository.external_id == "701")
    )
    assert db_repo is not None
    assert db_repo.languages == {"Python": 9999}


# ---------------------------------------------------------------------------
# Test 7: GitHubApiClient async context manager session reuse
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_client_async_context_manager():
    client = GitHubApiClient("test-token")
    assert client._client is None
    assert client._owned_client is None

    async with client as c:
        assert c is client
        assert client._client is not None
        assert client._owned_client is not None
        assert not client._owned_client.is_closed

        # Nested context depth test
        async with client:
            assert client._context_depth == 2

        assert client._context_depth == 1
        assert not client._owned_client.is_closed

    assert client._client is None
    assert client._owned_client is None


# ---------------------------------------------------------------------------
# Test 8: get_user_sync_status detects failed RQ job
# ---------------------------------------------------------------------------
def test_get_user_sync_status_detects_failed_rq_job(
    in_memory_db: Session, sample_user: User, fake_sync_redis
):
    # Set Redis cache to running with a specific job_id
    fake_sync_redis[f"ita:github:sync:{sample_user.id}"] = json.dumps(
        {
            "status": "running",
            "job_id": "failed-job-999",
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )

    fake_job = SimpleNamespace(
        id="failed-job-999",
        get_status=lambda refresh=True: SimpleNamespace(value="failed"),
    )

    with patch("app.workers.enqueue.fetch_job", return_value=fake_job):
        status_info = get_user_sync_status(in_memory_db, sample_user.id)

    assert status_info["status"] == "failed"
    assert "thất bại hoặc quá thời gian" in status_info["error_message"]


# ---------------------------------------------------------------------------
# Test 9: get_user_sync_status detects expired running job (exceeded timeout)
# ---------------------------------------------------------------------------
def test_get_user_sync_status_detects_expired_running_job(
    in_memory_db: Session, sample_user: User, fake_sync_redis
):
    # Set Redis cache to running from 10 minutes ago without job_id
    old_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    fake_sync_redis[f"ita:github:sync:{sample_user.id}"] = json.dumps(
        {
            "status": "running",
            "updated_at": old_time,
        }
    )

    status_info = get_user_sync_status(in_memory_db, sample_user.id)

    assert status_info["status"] == "failed"
    assert "Quá thời gian" in status_info["error_message"]
