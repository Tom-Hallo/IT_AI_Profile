"""Kiểm thử migration với PostgreSQL THẬT (Blueprint 9.3).

Mặc định bị bỏ qua. Chạy: RUN_INTEGRATION=1 pytest tests/db
Mỗi test dùng một database TẠM (xem conftest.py) nên có thể upgrade/downgrade thoải mái.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _head() -> str:
    script = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    return script.get_current_head()


def _stored_versions(url: str) -> list[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT version_num FROM alembic_version"))
            return [row[0] for row in rows]
    finally:
        engine.dispose()


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_current_is_empty_on_fresh_database(alembic_cli, temp_database_url):
    result = alembic_cli("current", database_url=temp_database_url)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""  # chưa áp dụng revision nào


def test_upgrade_head_then_current_reports_head(alembic_cli, temp_database_url):
    upgrade = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert upgrade.returncode == 0, upgrade.stderr

    current = alembic_cli("current", database_url=temp_database_url)
    assert current.returncode == 0, current.stderr
    assert f"{_head()} (head)" in current.stdout

    assert _stored_versions(temp_database_url) == [_head()]
    assert "alembic_version" in _tables(temp_database_url)


def test_upgrade_is_idempotent(alembic_cli, temp_database_url):
    assert alembic_cli("upgrade", "head", database_url=temp_database_url).returncode == 0
    assert alembic_cli("upgrade", "head", database_url=temp_database_url).returncode == 0
    assert _stored_versions(temp_database_url) == [_head()]


def test_downgrade_base_then_upgrade_again(alembic_cli, temp_database_url):
    assert alembic_cli("upgrade", "head", database_url=temp_database_url).returncode == 0
    down = alembic_cli("downgrade", "base", database_url=temp_database_url)
    assert down.returncode == 0, down.stderr
    assert _stored_versions(temp_database_url) == []

    up = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert up.returncode == 0, up.stderr
    assert _stored_versions(temp_database_url) == [_head()]


def test_check_reports_no_pending_model_changes(alembic_cli, temp_database_url):
    # Chưa có model nào, nên không có thay đổi chờ sinh migration.
    assert alembic_cli("upgrade", "head", database_url=temp_database_url).returncode == 0
    result = alembic_cli("check", database_url=temp_database_url)
    assert result.returncode == 0, result.stderr + result.stdout
