"""Fixture dùng chung cho test database (Database Engineer, D1).

Alembic luôn được chạy bằng TIẾN TRÌNH CON (`python -m alembic`) giống hệt cách người dùng gõ lệnh:
vừa kiểm tra đúng đường chạy thật, vừa tránh `fileConfig` của Alembic làm đổi cấu hình logging
của tiến trình pytest.
"""

import os
import subprocess
import sys
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]

AlembicRunner = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def alembic_cli() -> AlembicRunner:
    def run(
        *args: str, database_url: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        if database_url is not None:
            env["DATABASE_URL"] = database_url
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    return run


@pytest.fixture
def temp_database_url() -> Iterator[str]:
    """Tạo một database TẠM trên cùng máy chủ PostgreSQL rồi xóa khi xong.

    Nhờ vậy test migration (kể cả downgrade) không bao giờ đụng vào dữ liệu dev thật.
    Cần RUN_INTEGRATION=1 và tài khoản có quyền CREATEDB (user trong .env.example là superuser).
    """
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("cần RUN_INTEGRATION=1 và PostgreSQL đang chạy")

    base_url = make_url(settings.database_url.get_secret_value())
    name = f"ita_migration_test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(
        base_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        yield base_url.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
