"""Cấu hình test chung. Đặt biến môi trường trước khi import app.

Khi chạy integration test, sử dụng DATABASE_URL thật từ file .env.
Khi chạy unit test, sử dụng DATABASE_URL giả.
"""

import datetime
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

from cryptography.fernet import Fernet

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc  # noqa: UP017

# Bổ sung đường dẫn .venv vào CUỐI sys.path để hỗ trợ nạp tzdata trên Windows
_venv_site = Path(__file__).resolve().parent.parent / ".venv" / "Lib" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.append(str(_venv_site))

# Dự phòng mock DBAPI và Redis cho môi trường unit test cục bộ khi thiếu binary C driver
if os.environ.get("RUN_INTEGRATION") != "1":
    try:
        import psycopg  # noqa: F401
    except ImportError:
        m_psycopg = MagicMock()
        m_psycopg.__version__ = "3.3.6"
        m_psycopg.Error = type("Error", (Exception,), {})
        m_psycopg.OperationalError = type("OperationalError", (m_psycopg.Error,), {})
        m_psycopg.DatabaseError = type("DatabaseError", (m_psycopg.Error,), {})
        sys.modules.setdefault("psycopg", m_psycopg)
        sys.modules.setdefault("psycopg.pq", MagicMock())
        sys.modules.setdefault("psycopg.types", MagicMock())
        sys.modules.setdefault("psycopg.adapt", MagicMock())

    try:
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy.ext.compiler import compiles

        @compiles(JSONB, "sqlite")
        def compile_jsonb_sqlite(type_, compiler, **kw):
            return "JSON"
    except ImportError:
        pass

    try:
        import redis  # noqa: F401
    except ImportError:
        m_redis = MagicMock()
        m_redis.__path__ = []
        m_redis.exceptions.RedisError = type("RedisError", (Exception,), {})
        sys.modules.setdefault("redis", m_redis)
        sys.modules.setdefault("redis.client", m_redis.client)
        sys.modules.setdefault("redis.exceptions", m_redis.exceptions)

os.environ.setdefault("APP_ENV", "test")

if os.environ.get("RUN_INTEGRATION") != "1":
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://test:test-pass@127.0.0.1:5432/test_db",
    )

os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault(
    "GITHUB_TOKEN_ENCRYPTION_KEY",
    Fernet.generate_key().decode(),
)
