"""Tests for GitHub repository synchronization service (database persistence &
idempotence).
"""

import httpx
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.modules.assessments.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.cvs.models  # noqa: F401
import app.modules.github.models  # noqa: F401
import app.modules.roadmaps.models  # noqa: F401
import app.modules.users.models  # noqa: F401
from app.core.security import encrypt_token
from app.db.base import Base
from app.modules.auth.models import OAuthAccount
from app.modules.auth.service import disconnect_github, get_user_github_token
from app.modules.github.client import GitHubApiClient, GitHubRateLimitError
from app.modules.github.models import Repository, user_repository
from app.modules.github.service import (
    get_user_sync_status,
    sync_repositories_for_user,
)
from app.modules.users.models import User


@pytest.fixture
def in_memory_db():
    """Tạo database SQLite in-memory cho các bảng cần thiết."""
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

    # Đăng ký bảng vào SQLite schema ita
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        yield session

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_user(in_memory_db: Session) -> User:
    user = User(
        id=1,
        email="developer@example.com",
        full_name="Test Developer",
        hashed_password="test-only-placeholder-hash",
    )
    in_memory_db.add(user)
    in_memory_db.flush()

    oauth_account = OAuthAccount(
        id=1,
        user_id=user.id,
        provider="github",
        provider_user_id="123456",
        encrypted_access_token=encrypt_token("gho_test_valid_token"),
        scope="read:user user:email",
    )
    in_memory_db.add(oauth_account)
    in_memory_db.commit()
    return user


@pytest.fixture
def fake_sync_redis(monkeypatch):
    storage = {}

    class FakeRedis:
        def set(self, key, value, ex=None):
            storage[key] = value
            return True

        def get(self, key):
            return storage.get(key)

    monkeypatch.setattr(
        "app.modules.github.service.get_redis_connection",
        lambda: FakeRedis(),
    )


@pytest.mark.anyio
async def test_sync_user_with_zero_repositories(
    in_memory_db: Session, sample_user: User
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    result = await sync_repositories_for_user(in_memory_db, sample_user, client=client)

    assert result["status"] == "completed"
    assert result["synced_count"] == 0

    repos = in_memory_db.scalars(select(Repository)).all()
    assert len(repos) == 0


@pytest.mark.anyio
async def test_sync_user_with_repositories_and_languages(
    in_memory_db: Session, sample_user: User
):
    # Cấu hình user có quyền private hợp lệ để test sync cả public và private repo
    oauth = in_memory_db.scalars(
        select(OAuthAccount).where(OAuthAccount.user_id == sample_user.id)
    ).first()
    assert oauth is not None
    oauth.access_mode = "private_enabled"
    oauth.scope = "read:user user:email repo"
    in_memory_db.commit()

    fake_repos = [
        {
            "id": 1001,
            "name": "ai-profiler",
            "full_name": "developer/ai-profiler",
            "html_url": "https://github.com/developer/ai-profiler",
            "description": "AI Profiling tool",
            "private": False,
            "default_branch": "develop",
            "fork": False,
            "language": "Python",
            "stargazers_count": 42,
            "forks_count": 5,
            "open_issues_count": 2,
            "size": 1024,
            "archived": False,
            "disabled": False,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-11-01T00:00:00Z",
            "pushed_at": "2026-11-08T00:00:00Z",
            "owner": {"login": "developer"},
        },
        {
            "id": 1002,
            "name": "forked-react",
            "full_name": "developer/forked-react",
            "html_url": "https://github.com/developer/forked-react",
            "description": "Forked React repository",
            "private": True,
            "default_branch": "main",
            "fork": True,
            "language": "TypeScript",
            "stargazers_count": 1,
            "forks_count": 0,
            "open_issues_count": 0,
            "size": 2048,
            "archived": False,
            "disabled": False,
            "created_at": "2026-05-01T00:00:00Z",
            "updated_at": "2026-10-01T00:00:00Z",
            "pushed_at": "2026-10-05T00:00:00Z",
            "owner": {"login": "developer"},
            "parent": {"full_name": "facebook/react"},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/languages" in url_str:
            if "ai-profiler" in url_str:
                return httpx.Response(200, json={"Python": 185000, "Shell": 5000})
            return httpx.Response(200, json={"TypeScript": 92000, "JavaScript": 8000})
        return httpx.Response(200, json=fake_repos)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    result = await sync_repositories_for_user(in_memory_db, sample_user, client=client)

    assert result["status"] == "completed"
    assert result["synced_count"] == 2

    # Kiểm tra bảng repositories
    repos = in_memory_db.scalars(
        select(Repository).order_by(Repository.external_id)
    ).all()
    assert len(repos) == 2

    repo1 = repos[0]
    assert repo1.external_id == "1001"
    assert repo1.name == "ai-profiler"
    assert repo1.default_branch == "develop"
    assert repo1.is_fork is False
    assert repo1.fork_source is None
    assert repo1.languages == {"Python": 185000, "Shell": 5000}
    assert repo1.primary_language == "Python"
    assert repo1.stars_count == 42
    assert repo1.private is False

    repo2 = repos[1]
    assert repo2.external_id == "1002"
    assert repo2.name == "forked-react"
    assert repo2.is_fork is True
    assert repo2.fork_source == "facebook/react"
    assert repo2.private is True
    assert repo2.languages == {"TypeScript": 92000, "JavaScript": 8000}

    # Kiểm tra bảng pivot user_repository
    pivots = in_memory_db.execute(select(user_repository)).all()
    assert len(pivots) == 2
    assert all(p.user_id == sample_user.id for p in pivots)


@pytest.mark.anyio
async def test_sync_with_injected_client_in_public_only_mode_drops_private_repos(
    in_memory_db: Session, sample_user: User
):
    """Đảm bảo injected client không thể bypass public_only mode.

    Private repos trả về từ mock client phải bị loại bỏ và không được lưu DB.
    """
    oauth = in_memory_db.scalars(
        select(OAuthAccount).where(OAuthAccount.user_id == sample_user.id)
    ).first()
    assert oauth is not None
    oauth.access_mode = "public_only"
    oauth.scope = "read:user user:email"
    in_memory_db.commit()

    fake_repos = [
        {
            "id": 3001,
            "name": "public-repo",
            "full_name": "developer/public-repo",
            "html_url": "https://github.com/developer/public-repo",
            "description": "Public repo description",
            "private": False,
            "default_branch": "main",
            "fork": False,
            "language": "Python",
            "stargazers_count": 5,
            "forks_count": 1,
            "open_issues_count": 0,
            "size": 512,
            "archived": False,
            "disabled": False,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-11-01T00:00:00Z",
            "pushed_at": "2026-11-08T00:00:00Z",
            "owner": {"login": "developer"},
        },
        {
            "id": 3002,
            "name": "private-secret-repo",
            "full_name": "developer/private-secret-repo",
            "html_url": "https://github.com/developer/private-secret-repo",
            "description": "Private secret repo",
            "private": True,
            "default_branch": "main",
            "fork": False,
            "language": "TypeScript",
            "stargazers_count": 0,
            "forks_count": 0,
            "open_issues_count": 0,
            "size": 1024,
            "archived": False,
            "disabled": False,
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-11-01T00:00:00Z",
            "pushed_at": "2026-11-08T00:00:00Z",
            "owner": {"login": "developer"},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/languages" in url_str:
            return httpx.Response(200, json={"Python": 1000})
        return httpx.Response(200, json=fake_repos)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    result = await sync_repositories_for_user(in_memory_db, sample_user, client=client)

    assert result["status"] == "completed"
    assert result["synced_count"] == 1

    # Kiểm tra DB: chỉ public-repo được lưu, không lưu private-secret-repo
    repos = in_memory_db.scalars(select(Repository)).all()
    assert len(repos) == 1
    assert repos[0].external_id == "3001"
    assert repos[0].name == "public-repo"
    assert repos[0].private is False

    # Pivot table cũng chỉ trỏ tới public-repo
    pivots = in_memory_db.execute(select(user_repository)).all()
    assert len(pivots) == 1
    assert pivots[0].repository_id == repos[0].id


@pytest.mark.anyio
async def test_repeated_sync_is_idempotent_and_updates_data(
    in_memory_db: Session, sample_user: User
):
    initial_repos = [
        {
            "id": 2001,
            "name": "my-project",
            "full_name": "developer/my-project",
            "html_url": "https://github.com/developer/my-project",
            "description": "Initial description",
            "private": False,
            "default_branch": "main",
            "fork": False,
            "language": "Python",
            "stargazers_count": 10,
            "owner": {"login": "developer"},
        }
    ]

    updated_repos = [
        {
            "id": 2001,
            "name": "my-renamed-project",
            "full_name": "developer/my-renamed-project",
            "html_url": "https://github.com/developer/my-renamed-project",
            "description": "Updated description",
            "private": False,
            "default_branch": "main",
            "fork": False,
            "language": "Python",
            "stargazers_count": 25,  # Stars tăng
            "owner": {"login": "developer"},
        }
    ]

    # Lần 1: sync bản đầu
    def handler1(request: httpx.Request) -> httpx.Response:
        if "/languages" in str(request.url):
            return httpx.Response(200, json={"Python": 1000})
        return httpx.Response(200, json=initial_repos)

    client1 = GitHubApiClient(
        "test-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler1)),
    )
    await sync_repositories_for_user(in_memory_db, sample_user, client=client1)

    repos_after_first = in_memory_db.scalars(select(Repository)).all()
    assert len(repos_after_first) == 1
    assert repos_after_first[0].name == "my-project"
    assert repos_after_first[0].stars_count == 10

    # Lần 2: sync lại với dữ liệu mới từ GitHub
    def handler2(request: httpx.Request) -> httpx.Response:
        if "/languages" in str(request.url):
            return httpx.Response(200, json={"Python": 1500})
        return httpx.Response(200, json=updated_repos)

    client2 = GitHubApiClient(
        "test-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler2)),
    )
    await sync_repositories_for_user(in_memory_db, sample_user, client=client2)

    repos_after_second = in_memory_db.scalars(select(Repository)).all()
    # Không tạo bản ghi trùng lặp (vẫn là 1 record)
    assert len(repos_after_second) == 1
    updated_repo = repos_after_second[0]
    assert updated_repo.external_id == "2001"
    assert updated_repo.name == "my-renamed-project"
    assert updated_repo.description == "Updated description"
    assert updated_repo.stars_count == 25
    assert updated_repo.languages == {"Python": 1500}


@pytest.mark.anyio
async def test_sync_rate_limit_failure_rolls_back(
    in_memory_db: Session,
    sample_user: User,
    fake_sync_redis,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "rate limit exceeded"},
            headers={"x-ratelimit-remaining": "0"},
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    with pytest.raises(GitHubRateLimitError):
        await sync_repositories_for_user(in_memory_db, sample_user, client=client)

    status_info = get_user_sync_status(in_memory_db, sample_user.id)
    assert status_info["status"] == "failed"
    assert status_info["error_message"] is not None


def test_disconnect_github_account(in_memory_db: Session, sample_user: User):
    token, scope = get_user_github_token(in_memory_db, sample_user.id)
    assert token == "gho_test_valid_token"
    assert scope == "read:user user:email"

    success = disconnect_github(in_memory_db, sample_user.id)
    assert success is True

    token_after, scope_after = get_user_github_token(in_memory_db, sample_user.id)
    assert token_after is None
    assert scope_after is None
