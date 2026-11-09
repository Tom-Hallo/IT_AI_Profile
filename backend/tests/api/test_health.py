import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.api import health as health_module
from app.core import redis as redis_core
from app.db import session as db_session
from app.main import create_app

SECRET_MARKERS = [
    "test-pass",
    "postgresql",
    "redis://",
    "127.0.0.1",
    "Traceback",
    "test_db",
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _ok() -> None:
    return None


def test_health_ok_when_all_dependencies_healthy(client, monkeypatch):
    monkeypatch.setattr(db_session, "check_database", _ok)
    monkeypatch.setattr(redis_core, "check_redis", _ok)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "backend",
        "version": "0.1.0",
        "checks": {"database": "ok", "redis": "ok"},
    }


@pytest.mark.parametrize(
    ("db_fails", "redis_fails", "expected"),
    [
        (True, False, {"database": "fail", "redis": "ok"}),
        (False, True, {"database": "ok", "redis": "fail"}),
        (True, True, {"database": "fail", "redis": "fail"}),
    ],
)
def test_health_503_when_dependency_fails(
    client, monkeypatch, db_fails, redis_fails, expected
):
    def boom() -> None:
        raise RuntimeError(
            (
                "password authentication failed for "
                "postgresql://test:test-pass@127.0.0.1/test_db"
            )
        )

    monkeypatch.setattr(db_session, "check_database", boom if db_fails else _ok)
    monkeypatch.setattr(redis_core, "check_redis", boom if redis_fails else _ok)

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"] == expected


def test_503_body_does_not_leak_sensitive_information(client, monkeypatch):
    def boom() -> None:
        raise RuntimeError(
            "could not connect postgresql://test:test-pass@127.0.0.1/test_db"
        )

    monkeypatch.setattr(db_session, "check_database", boom)
    monkeypatch.setattr(redis_core, "check_redis", boom)

    text = client.get("/api/v1/health").text

    for marker in SECRET_MARKERS:
        assert marker not in text


def test_failure_log_does_not_contain_secret(client, monkeypatch, caplog):
    def boom() -> None:
        raise RuntimeError("postgresql://test:test-pass@127.0.0.1/test_db")

    monkeypatch.setattr(db_session, "check_database", boom)
    monkeypatch.setattr(redis_core, "check_redis", _ok)

    with caplog.at_level("WARNING"):
        client.get("/api/v1/health")

    assert "test-pass" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_slow_dependency_is_cut_off_by_timeout(monkeypatch):
    """Dependency treo 1s bị cắt ở 0.2s; endpoint trả 503 ngay, không chờ thread treo.
    """

    def hang() -> None:
        time.sleep(1.0)

    monkeypatch.setattr(health_module, "CHECK_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(db_session, "check_database", hang)
    monkeypatch.setattr(redis_core, "check_redis", _ok)

    # Dùng vòng lặp thủ công: đo thời gian TRƯỚC khi đóng vòng lặp (đóng vòng lặp sẽ chờ
    # thread giả lập đang ngủ, đó là hạn chế của test chứ không phải của endpoint).
    loop = asyncio.new_event_loop()
    try:
        started = time.monotonic()
        response = loop.run_until_complete(health_module.health())
        elapsed = time.monotonic() - started
    finally:
        loop.close()

    assert response.status_code == 503
    assert json.loads(response.body)["checks"] == {"database": "fail", "redis": "ok"}
    assert elapsed < 0.7


def test_checks_run_concurrently():
    """Hai kiểm tra chậm 0.3s chạy song song, tổng khoảng 0.3s chứ không phải 0.6s."""

    def slow() -> None:
        time.sleep(0.3)

    async def run() -> float:
        started = time.monotonic()
        await asyncio.gather(
            health_module._run_check("a", slow),
            health_module._run_check("b", slow),
        )
        return time.monotonic() - started

    assert asyncio.run(run()) < 0.55


def test_health_is_not_exposed_without_api_prefix(client):
    assert client.get("/health").status_code == 404
