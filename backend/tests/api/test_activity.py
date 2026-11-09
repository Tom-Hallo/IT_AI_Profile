"""Activity API auth and validation smoke tests."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.main import create_app


def test_activity_unauthenticated():
    app = create_app()
    with TestClient(app) as client:
        result = client.get("/api/v1/repositories/1/activity/analysis?mode=preset&preset=1m")
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
        result = client.get("/api/v1/repositories/9/activity/analysis?mode=month&month=2026-10")
    assert result.status_code == 200
    assert result.json()["activity"]["commits"] == 2
    assert fake.await_args.args[1:3] == (9, 7)
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
