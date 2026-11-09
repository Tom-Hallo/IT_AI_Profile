"""Tests for GitHub API router endpoints (authorization, sync, listing, details)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.modules.assessments.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.cvs.models  # noqa: F401
import app.modules.github.models  # noqa: F401
import app.modules.roadmaps.models  # noqa: F401
import app.modules.users.models  # noqa: F401
from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.github import router as github_router
from app.modules.users.models import User


@pytest.fixture
def mock_db():
    db = MagicMock()
    return db


@pytest.fixture
def test_user():
    return User(
        id=1,
        email="developer@example.com",
        full_name="Test Developer",
        hashed_password=None,
    )


@pytest.fixture
def other_user():
    return User(
        id=2,
        email="other@example.com",
        full_name="Other Developer",
        hashed_password=None,
    )


@pytest.fixture
def app():
    api = FastAPI()
    api.include_router(github_router.router, prefix="/api/v1")
    return api


@pytest.fixture
def client(app):
    return TestClient(app)


def test_unauthenticated_requests_return_401(client):
    res_sync = client.post("/api/v1/github/sync")
    assert res_sync.status_code == 401

    res_status = client.get("/api/v1/github/sync/status")
    assert res_status.status_code == 401

    res_repos = client.get("/api/v1/github/repositories")
    assert res_repos.status_code == 401

    res_detail = client.get("/api/v1/github/repositories/1")
    assert res_detail.status_code == 401


def test_sync_without_github_token_returns_400(app, test_user):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: object()

    with patch(
        "app.modules.github.router.get_user_github_token", return_value=(None, None)
    ):
        client = TestClient(app)
        res = client.post("/api/v1/github/sync")
        assert res.status_code == 400
        assert "Tài khoản chưa kết nối GitHub" in res.json()["detail"]


def test_sync_trigger_conflict_when_already_running(app, test_user):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: object()

    with (
        patch(
            "app.modules.github.router.get_user_github_token",
            return_value=("token", "repo"),
        ),
        patch(
            "app.modules.github.router.get_user_sync_status",
            return_value={"status": "running"},
        ),
    ):
        client = TestClient(app)
        res = client.post("/api/v1/github/sync")
        assert res.status_code == 409
        assert "Tiến trình đồng bộ đang chạy" in res.json()["detail"]


def test_sync_trigger_background_enqueues_job(app, test_user):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: object()

    fake_job = SimpleNamespace(id="job-12345")

    with (
        patch(
            "app.modules.github.router.get_user_github_token",
            return_value=("token", "repo"),
        ),
        patch(
            "app.modules.github.router.get_user_sync_status",
            return_value={"status": "idle"},
        ),
        patch("app.modules.github.router.enqueue_task", return_value=fake_job),
        patch("app.modules.github.router.set_sync_status_cache") as mock_cache,
    ):
        client = TestClient(app)
        res = client.post("/api/v1/github/sync?background=true")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "running"
        assert data["job_id"] == "job-12345"
        mock_cache.assert_called_once_with(1, status="running")


@pytest.mark.anyio
async def test_sync_trigger_synchronous(app, test_user):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: object()

    async def fake_sync(db, user):
        return {
            "status": "completed",
            "synced_count": 5,
            "last_synced_at": "2026-11-08T12:00:00Z",
        }

    with (
        patch(
            "app.modules.github.router.get_user_github_token",
            return_value=("token", "repo"),
        ),
        patch(
            "app.modules.github.router.get_user_sync_status",
            return_value={"status": "idle"},
        ),
        patch(
            "app.modules.github.router.sync_repositories_for_user",
            side_effect=fake_sync,
        ),
    ):
        client = TestClient(app)
        res = client.post("/api/v1/github/sync?background=false")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["synced_count"] == 5
        assert data["last_synced_at"] == "2026-11-08T12:00:00Z"


def test_get_sync_status_endpoint(app, test_user):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: object()

    fake_status = {
        "status": "completed",
        "is_connected": True,
        "has_private_scope": True,
        "total_repositories": 10,
        "last_synced_at": "2026-11-08T12:00:00Z",
        "error_message": None,
    }

    with patch(
        "app.modules.github.router.get_user_sync_status", return_value=fake_status
    ):
        client = TestClient(app)
        res = client.get("/api/v1/github/sync/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["is_connected"] is True
        assert data["total_repositories"] == 10


def test_list_repositories_endpoint(app, test_user, mock_db):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: mock_db

    fake_repo = SimpleNamespace(
        id=1,
        external_id="101",
        name="awesome-project",
        full_name="developer/awesome-project",
        html_url="https://github.com/developer/awesome-project",
        description="An awesome project",
        private=False,
        default_branch="main",
        is_fork=False,
        fork_source=None,
        primary_language="Python",
        languages={"Python": 1000},
        stars_count=15,
        forks_count=2,
        open_issues_count=0,
        size_kb=512,
        archived=False,
        disabled=False,
        pushed_at=datetime(2026, 11, 8, tzinfo=UTC),
        github_created_at=datetime(2026, 1, 1, tzinfo=UTC),
        github_updated_at=datetime(2026, 11, 1, tzinfo=UTC),
        last_synced_at=datetime(2026, 11, 8, tzinfo=UTC),
        sync_status="synced",
    )

    mock_db.scalars.return_value.all.return_value = [fake_repo]
    mock_db.scalar.return_value = 1

    client = TestClient(app)
    res = client.get("/api/v1/github/repositories?page=1&per_page=20")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "awesome-project"
    assert data["items"][0]["languages"] == {"Python": 1000}


def test_get_repository_details_success(app, test_user, mock_db):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: mock_db

    fake_repo = SimpleNamespace(
        id=42,
        external_id="202",
        name="my-lib",
        full_name="developer/my-lib",
        html_url="https://github.com/developer/my-lib",
        description="A library",
        private=False,
        default_branch="main",
        is_fork=False,
        fork_source=None,
        primary_language="TypeScript",
        languages={"TypeScript": 50000},
        stars_count=100,
        forks_count=10,
        open_issues_count=1,
        size_kb=2048,
        archived=False,
        disabled=False,
        pushed_at=datetime(2026, 11, 8, tzinfo=UTC),
        github_created_at=datetime(2026, 1, 1, tzinfo=UTC),
        github_updated_at=datetime(2026, 11, 1, tzinfo=UTC),
        last_synced_at=datetime(2026, 11, 8, tzinfo=UTC),
        sync_status="synced",
    )

    mock_db.scalar.return_value = fake_repo

    client = TestClient(app)
    res = client.get("/api/v1/github/repositories/42")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 42
    assert data["name"] == "my-lib"
    assert data["languages"] == {"TypeScript": 50000}


def test_user_isolation_cannot_access_other_users_repository(app, test_user, mock_db):
    """Kiểm tra user A không thể xem repository của user B (trả về 404 Not Found)."""
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: mock_db

    mock_db.scalar.return_value = None

    client = TestClient(app)
    res = client.get("/api/v1/github/repositories/999")
    assert res.status_code == 404
    assert (
        "Không tìm thấy repository hoặc bạn không có quyền truy cập"
        in res.json()["detail"]
    )


def test_tokens_never_leaked_in_responses(app, test_user, mock_db):
    """Kiểm tra không có token hay secret nào bị rò rỉ trong API responses."""
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: mock_db

    fake_repo = SimpleNamespace(
        id=1,
        external_id="101",
        name="test",
        full_name="user/test",
        html_url="https://github.com/user/test",
        description=None,
        private=False,
        default_branch="main",
        is_fork=False,
        fork_source=None,
        primary_language=None,
        languages=None,
        stars_count=0,
        forks_count=0,
        open_issues_count=0,
        size_kb=0,
        archived=False,
        disabled=False,
        pushed_at=None,
        github_created_at=None,
        github_updated_at=None,
        last_synced_at=None,
        sync_status="synced",
    )

    mock_db.scalar.return_value = fake_repo

    client = TestClient(app)
    res = client.get("/api/v1/github/repositories/1")
    response_text = res.text
    assert "token" not in response_text.lower()
    assert "gho_" not in response_text
    assert "secret" not in response_text.lower()
