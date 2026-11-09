"""Kiểm tra cấu hình Alembic mà KHÔNG cần PostgreSQL đang chạy."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))


def test_there_is_exactly_one_head():
    # Nhiều head = hai nhánh cùng thêm migration; phải `alembic merge heads` trước khi merge PR.
    assert len(_script_directory().get_heads()) == 1


def test_baseline_is_first_and_empty():
    script = _script_directory()
    base = script.get_revision(script.get_base())
    assert base.down_revision is None
    source = Path(base.path).read_text(encoding="utf-8")
    # PBI-001 không tạo bảng nghiệp vụ (Blueprint D10): baseline không được chứa thao tác schema.
    for forbidden in ("create_table", "add_column", "execute("):
        assert forbidden not in source


def test_migration_files_follow_naming_template():
    for path in (BACKEND_DIR / "migrations" / "versions").glob("*.py"):
        assert len(path.name.split("_")) >= 4, path.name
        assert path.name[:8].isdigit(), path.name  # YYYYMMDD_HHMM_<rev>_<slug>.py


def test_alembic_ini_has_no_connection_url():
    ini = (BACKEND_DIR / "alembic.ini").read_text(encoding="utf-8")
    uncommented = [
        line for line in ini.splitlines() if not line.lstrip().startswith("#")
    ]
    assert not any(
        "postgresql" in line or "sqlalchemy.url" in line for line in uncommented
    )


def test_offline_sql_generation_works_without_database(alembic_cli):
    # Chế độ --sql không kết nối DB, nên chạy được cả khi PostgreSQL tắt.
    result = alembic_cli("upgrade", "head", "--sql")
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE alembic_version" in result.stdout
    assert "INSERT INTO alembic_version" in result.stdout
    # Không rò rỉ URL/mật khẩu ra output.
    assert "test-pass" not in result.stdout + result.stderr
    assert "postgresql+psycopg" not in result.stdout + result.stderr


def test_unreachable_database_fails_without_leaking_password(alembic_cli):
    # Cổng 1 không có dịch vụ nào: kết nối bị từ chối ngay, không cần PostgreSQL đang chạy.
    bad_url = "postgresql+psycopg://ita:SuperSecret123@127.0.0.1:1/it_ai_profile"
    result = alembic_cli("upgrade", "head", database_url=bad_url)
    assert result.returncode != 0
    assert "SuperSecret123" not in result.stdout + result.stderr


def test_alembic_ini_and_template_are_ascii_only():
    """Alembic doc `alembic.ini` bang bang ma mac dinh cua he dieu hanh (cp1252 tren Windows).

    Ky tu co dau trong file nay lam MOI lenh `alembic` bi UnicodeDecodeError tren Windows.
    """
    for path in (
        BACKEND_DIR / "alembic.ini",
        BACKEND_DIR / "migrations" / "script.py.mako",
    ):
        path.read_bytes().decode(
            "ascii"
        )  # nem UnicodeDecodeError neu co ky tu non-ASCII
