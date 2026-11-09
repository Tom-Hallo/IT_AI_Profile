"""Activity API auth, validation, service layer, and GitHub error handling tests (PBI-010)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.main import create_app
from app.modules.github.models import Repository
from app.services.activity import _collect_pull_requests_in_range, analyze


def test_activity_unauthenticated():
    app = create_app()
    with TestClient(app) as client:
        result = client.get(
            "/api/v1/repositories/1/activity/analysis?mode=preset&preset=1m"
        )
    assert result.status_code == 401


def test_activity_invalid_mode():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: object()
    try:
        with TestClient(app) as client:
            result = client.get("/api/v1/repositories/1/activity/analysis?mode=invalid")
        assert result.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_activity_authenticated(monkeypatch):
    from app.api import activity

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: type("User", (), {"id": 7})()
    app.dependency_overrides[get_session] = lambda: object()
    fake = AsyncMock(return_value={"activity": {"commits": 2}})
    monkeypatch.setattr(activity, "analyze", fake)
    with TestClient(app) as client:
        result = client.get(
            "/api/v1/repositories/9/activity/analysis?mode=month&month=2026-10"
        )
    assert result.status_code == 200
    assert result.json()["activity"]["commits"] == 2
    assert fake.await_args.args[1:3] == (9, 7)
    app.dependency_overrides.clear()


def test_activity_year_mode_authenticated(monkeypatch):
    from app.api import activity

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: type("User", (), {"id": 7})()
    app.dependency_overrides[get_session] = lambda: object()
    fake = AsyncMock(return_value={"activity": {"commits": 10}})
    monkeypatch.setattr(activity, "analyze", fake)
    with TestClient(app) as client:
        result = client.get(
            "/api/v1/repositories/9/activity/analysis?mode=year&year=2026"
        )
    assert result.status_code == 200
    assert result.json()["activity"]["commits"] == 10
    app.dependency_overrides.clear()


def test_activity_invalid_timezone(monkeypatch):
    from app.api import activity

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: type("User", (), {"id": 7})()
    app.dependency_overrides[get_session] = lambda: object()
    fake = AsyncMock()
    monkeypatch.setattr(activity, "analyze", fake)
    with TestClient(app) as client:
        result = client.get(
            "/api/v1/repositories/9/activity/analysis?mode=month&month=2026-10&timezone=Bad/Zone"
        )
    assert result.status_code == 422
    fake.assert_not_awaited()
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_analyze_unauthorized_repo_raises_404():
    mock_db = MagicMock()
    mock_db.scalar.return_value = None  # User has no access to repository

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    with pytest.raises(HTTPException) as exc_info:
        await analyze(mock_db, repository_id=999, user_id=1, start=start, end=end)
    assert exc_info.value.status_code == 404
    assert "Repository not found or access denied" in exc_info.value.detail


@pytest.mark.anyio
async def test_analyze_incomplete_sync_raises_409():
    mock_db = MagicMock()
    repo = MagicMock(spec=Repository)
    repo.last_synced_at = None
    repo.sync_status = "pending"
    mock_db.scalar.return_value = repo

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    with pytest.raises(HTTPException) as exc_info:
        await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert exc_info.value.status_code == 409
    assert "Repository sync is incomplete" in exc_info.value.detail


@pytest.mark.anyio
async def test_analyze_private_repo_without_consent_raises_403(monkeypatch):
    mock_db = MagicMock()
    repo = MagicMock(spec=Repository)
    repo.last_synced_at = datetime(2026, 11, 1, tzinfo=UTC)
    repo.sync_status = "synced"
    repo.private = True
    repo.full_name = "owner/secret-repo"
    mock_db.scalar.return_value = repo

    # Token only has read:user scope
    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    with pytest.raises(HTTPException) as exc_info:
        await analyze(mock_db, repository_id=1, user_id=1, start=start, end=end)
    assert exc_info.value.status_code == 403
    assert "requires 'repo' OAuth scope consent" in exc_info.value.detail


@pytest.mark.anyio
async def test_analyze_empty_activity_period(monkeypatch):
    mock_db = MagicMock()
    repo = MagicMock(spec=Repository)
    repo.last_synced_at = datetime(2026, 11, 1, tzinfo=UTC)
    repo.sync_status = "synced"
    repo.private = False
    repo.full_name = "owner/public-repo"
    mock_db.scalar.return_value = repo

    monkeypatch.setattr(
        "app.services.activity.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    # Empty commits and PRs
    mock_response = MagicMock()
    mock_response.json.return_value = []
    fake_client = AsyncMock()
    fake_client._request.return_value = mock_response

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
async def test_pull_requests_pagination_stops_before_start():
    fake_client = AsyncMock()
    # Batch with PRs:
    # 1. 2026-10-15 (in range)
    # 2. 2026-09-20 (older than start)
    # 3. 2026-08-10 (even older)
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"created_at": "2026-10-15T10:00:00Z"},
        {"created_at": "2026-09-20T10:00:00Z"},
        {"created_at": "2026-08-10T10:00:00Z"},
    ]
    fake_client._request.return_value = mock_response

    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 11, 1, tzinfo=UTC)

    count = await _collect_pull_requests_in_range(
        fake_client, "/repos/owner/repo", start, end
    )
    assert count == 1
    # Only 1 page request made because it cleanly stopped upon seeing created_at < start
    assert fake_client._request.call_count == 1
