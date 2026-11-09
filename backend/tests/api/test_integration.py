"""Kiểm thử tích hợp với PostgreSQL và Redis THẬT.

Mặc định bị bỏ qua. Chạy khi có DB/Redis: RUN_INTEGRATION=1 pytest
tests/api/test_integration.py
(DATABASE_URL và REDIS_URL phải trỏ tới dịch vụ đang chạy).
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.core import redis as redis_core
from app.db import session as db_session
from app.main import create_app

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="cần RUN_INTEGRATION=1 và DB/Redis đang chạy",
)


def test_check_database_succeeds_with_real_postgres():
    db_session.check_database()


def test_check_redis_succeeds_with_real_redis():
    redis_core.check_redis()


def test_redis_connection_returns_bytes_not_str():
    conn = redis_core.get_redis_connection()
    conn.set("it_ai_profile:test", "x", ex=30)
    assert conn.get("it_ai_profile:test") == b"x"


def test_get_session_runs_a_query():
    from sqlalchemy import text

    session = next(db_session.get_session())
    assert session.execute(text("SELECT 1")).scalar() == 1
    session.close()


def test_health_endpoint_reports_ok_with_real_services():
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "redis": "ok"}
