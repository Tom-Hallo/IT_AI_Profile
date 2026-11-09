"""Test engine/session (không cần PostgreSQL đang chạy, trừ nhóm tích hợp ở cuối)."""

import ast
import importlib
import os
import pkgutil
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db import session as db_session
from app.db.base import NAMING_CONVENTION, Base

APP_DIR = Path(__file__).resolve().parents[2] / "app"


# --- Cấu hình engine ---------------------------------------------------------------------------


def test_engine_uses_psycopg_v3_and_settings_url():
    assert db_session.engine.dialect.driver == "psycopg"
    rendered = db_session.engine.url.render_as_string(hide_password=False)
    assert rendered == settings.database_url.get_secret_value()


def test_only_db_session_creates_an_engine():
    """Quy tắc Blueprint 1.4: không module nào tự tạo kết nối riêng tới DB."""
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if re.search(r"\bcreate_engine\(", path.read_text(encoding="utf-8"))
        and path != APP_DIR / "db" / "session.py"
    ]
    assert offenders == []


def test_alembic_env_does_not_read_environment_or_hardcode_url():
    """env.py phải lấy URL qua settings/engine: không import os, không chứa chuỗi URL."""
    source = (Path(__file__).resolve().parents[2] / "migrations" / "env.py").read_text("utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "os" not in imported
    string_constants = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any("postgresql" in value.lower() for value in string_constants)


def test_naming_convention_is_set_before_any_table_exists():
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}


<<<<<<< HEAD
def test_business_tables_defined_in_pbi_002_and_pbi_005():
    """Import all modules and verify the 7 PBI-002/PBI-005 tables."""
=======
def test_business_tables_defined_in_pbi_002():
    """Import all modules and verify Base.metadata has the 6 PBI-002 tables."""
>>>>>>> 7782749 (T065DDA: fix trang demo)
    import app

    for module in pkgutil.walk_packages(app.__path__, prefix="app."):
        importlib.import_module(module.name)
<<<<<<< HEAD

=======
>>>>>>> 7782749 (T065DDA: fix trang demo)
    expected_tables = {
        "ita.users",
        "ita.repositories",
        "ita.assessments",
        "ita.cvs",
        "ita.roadmaps",
        "ita.user_repository",
<<<<<<< HEAD
        "ita.user_oauth_accounts",
    }

=======
    }
>>>>>>> 7782749 (T065DDA: fix trang demo)
    assert set(Base.metadata.tables.keys()) == expected_tables


# --- get_session / session_scope (dùng SQLite trong bộ nhớ, không cần PostgreSQL) -----------


@pytest.fixture
def sqlite_session_factory(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE items (v INTEGER)"))
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", factory)
    yield engine
    engine.dispose()


def _count(engine) -> int:
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM items")).scalar_one()


def test_session_scope_commits_on_success(sqlite_session_factory):
    with db_session.session_scope() as session:
        session.execute(text("INSERT INTO items VALUES (1)"))
    assert _count(sqlite_session_factory) == 1


def test_session_scope_rolls_back_and_reraises_on_error(sqlite_session_factory):
    with pytest.raises(ValueError, match="boom"):
        with db_session.session_scope() as session:
            session.execute(text("INSERT INTO items VALUES (1)"))
            raise ValueError("boom")
    assert _count(sqlite_session_factory) == 0


def test_get_session_does_not_autocommit(sqlite_session_factory):
    generator = db_session.get_session()
    session = next(generator)
    session.execute(text("INSERT INTO items VALUES (1)"))
    generator.close()  # kết thúc request mà chưa commit
    assert _count(sqlite_session_factory) == 0


def test_get_session_commits_only_when_caller_commits(sqlite_session_factory):
    generator = db_session.get_session()
    session = next(generator)
    session.execute(text("INSERT INTO items VALUES (1)"))
    session.commit()
    generator.close()
    assert _count(sqlite_session_factory) == 1


# --- check_database khi DB không tới được -----------------------------------------------------


def test_check_database_raises_when_server_unreachable(monkeypatch):
    # Cổng 1 không có dịch vụ nào lắng nghe: từ chối kết nối ngay, không cần chờ.
    dead = create_engine(
        "postgresql+psycopg://u:p@127.0.0.1:1/x", connect_args={"connect_timeout": 1}
    )
    monkeypatch.setattr(db_session, "engine", dead)
    with pytest.raises(OperationalError):
        db_session.check_database()
    dead.dispose()


# --- Tích hợp với PostgreSQL thật (RUN_INTEGRATION=1) ------------------------------------------

integration = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1", reason="cần RUN_INTEGRATION=1 và PostgreSQL đang chạy"
)


@integration
def test_session_scope_against_real_postgres_commits_and_rolls_back():
    with db_session.session_scope() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1

    with pytest.raises(RuntimeError):
        with db_session.session_scope() as session:
            session.execute(text("SELECT 1"))
            raise RuntimeError("giả lập lỗi trong task")

    # Sau lỗi, kết nối trả về pool vẫn dùng được.
    db_session.check_database()


@integration
def test_server_is_postgresql_17_or_newer():
    with db_session.engine.connect() as connection:
        version_num = connection.execute(text("SHOW server_version_num")).scalar_one()
    assert int(version_num) >= 170000
