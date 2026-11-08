"""Kiem thu migration voi PostgreSQL THAT (Blueprint 9.3).

Mac dinh bi bo qua. Chay: RUN_INTEGRATION=1 pytest tests/db
Moi test dung mot database TAM (xem conftest.py) nen co the upgrade/downgrade thoai mai.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCHEMA = "ita"
EXPECTED_TABLES = {
    "users",
    "repositories",
    "assessments",
    "cvs",
    "roadmaps",
    "user_repository",
}


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


def _tables_in_schema(url: str, schema: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names(schema=schema))
    finally:
        engine.dispose()


def _tables(url: str) -> set[str]:
    """Backward-compatible: returns public schema tables (for alembic_version)."""
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# TC01 - fresh DB has no revisions
# ---------------------------------------------------------------------------
def test_current_is_empty_on_fresh_database(alembic_cli, temp_database_url):
    result = alembic_cli("current", database_url=temp_database_url)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""  # no revision applied yet


# ---------------------------------------------------------------------------
# TC02 - upgrade head -> reports correct head
# ---------------------------------------------------------------------------
def test_upgrade_head_then_current_reports_head(alembic_cli, temp_database_url):
    upgrade = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert upgrade.returncode == 0, upgrade.stderr

    current = alembic_cli("current", database_url=temp_database_url)
    assert current.returncode == 0, current.stderr
    assert f"{_head()} (head)" in current.stdout

    assert _stored_versions(temp_database_url) == [_head()]
    assert "alembic_version" in _tables(temp_database_url)


# ---------------------------------------------------------------------------
# TC03 - all business tables are created in the `ita` schema
# ---------------------------------------------------------------------------
def test_all_tables_created_in_ita_schema(alembic_cli, temp_database_url):
    upgrade = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert upgrade.returncode == 0, upgrade.stderr

    tables = _tables_in_schema(temp_database_url, SCHEMA)
    missing = EXPECTED_TABLES - tables
    assert not missing, f"Tables missing from schema '{SCHEMA}': {missing}"


# ---------------------------------------------------------------------------
# TC04 - upgrade is idempotent
# ---------------------------------------------------------------------------
def test_upgrade_is_idempotent(alembic_cli, temp_database_url):
    assert alembic_cli("upgrade", "head", database_url=temp_database_url).returncode == 0
    assert alembic_cli("upgrade", "head", database_url=temp_database_url).returncode == 0
    assert _stored_versions(temp_database_url) == [_head()]


# ---------------------------------------------------------------------------
# TC05 - downgrade base clears all business tables, re-upgrade succeeds
# ---------------------------------------------------------------------------
def test_downgrade_base_then_upgrade_again(alembic_cli, temp_database_url):
    assert alembic_cli("upgrade", "head", database_url=temp_database_url).returncode == 0

    down = alembic_cli("downgrade", "base", database_url=temp_database_url)
    assert down.returncode == 0, down.stderr
    assert _stored_versions(temp_database_url) == []

    # All business tables should be gone after downgrade
    tables = _tables_in_schema(temp_database_url, SCHEMA)
    remaining = EXPECTED_TABLES & tables
    assert not remaining, f"Tables still present after downgrade: {remaining}"

    up = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert up.returncode == 0, up.stderr
    assert _stored_versions(temp_database_url) == [_head()]


# ---------------------------------------------------------------------------
# TC06 - alembic check reports no pending model changes
# ---------------------------------------------------------------------------
def test_check_reports_no_pending_model_changes(alembic_cli, temp_database_url):
    assert alembic_cli("upgrade", "head", database_url=temp_database_url).returncode == 0
    result = alembic_cli("check", database_url=temp_database_url)
    assert result.returncode == 0, result.stderr + result.stdout


# ---------------------------------------------------------------------------
# TC07 - basic CRUD: insert valid rows, check constraints
# ---------------------------------------------------------------------------
def test_basic_crud_and_constraints(alembic_cli, temp_database_url):
    """Insert valid rows into each domain table and verify FK / unique constraints."""
    import pytest as _pytest
    from sqlalchemy import text as _text

    assert alembic_cli("upgrade", "head", database_url=temp_database_url).returncode == 0

    engine = create_engine(temp_database_url)
    try:
        with engine.begin() as conn:
            # Insert a user
            conn.execute(
                _text(
                    "INSERT INTO ita.users (email, full_name, hashed_password) VALUES (:e, :n, :p)"
                ),
                {"e": "alice@example.com", "n": "Alice", "p": "hash_placeholder"},
            )
            user_id = conn.execute(
                _text("SELECT id FROM ita.users WHERE email = 'alice@example.com'")
            ).scalar_one()

            # Insert a repository
            conn.execute(
                _text(
                    "INSERT INTO ita.repositories (owner_id, external_id, name, html_url) "
                    "VALUES (:oid, :eid, :n, :url)"
                ),
                {
                    "oid": user_id,
                    "eid": "gh:12345",
                    "n": "my-repo",
                    "url": "https://github.com/alice/my-repo",
                },
            )
            repo_id = conn.execute(
                _text("SELECT id FROM ita.repositories WHERE external_id = 'gh:12345'")
            ).scalar_one()

            # Insert an assessment with valid score
            conn.execute(
                _text("INSERT INTO ita.assessments (user_id, type, score) VALUES (:uid, :t, :s)"),
                {"uid": user_id, "t": "python", "s": 85.5},
            )

            # Insert a CV
            conn.execute(
                _text("INSERT INTO ita.cvs (user_id, content) VALUES (:uid, :c)"),
                {"uid": user_id, "c": '{"skills": ["Python"]}'},
            )

            # Insert a roadmap
            conn.execute(
                _text("INSERT INTO ita.roadmaps (user_id, title, data) VALUES (:uid, :t, :d)"),
                {"uid": user_id, "t": "My Roadmap", "d": '{"steps": []}'},
            )

            # Pivot
            conn.execute(
                _text(
                    "INSERT INTO ita.user_repository (user_id, repository_id) VALUES (:uid, :rid)"
                ),
                {"uid": user_id, "rid": repo_id},
            )

        # --- Constraint checks ---
        engine2 = create_engine(temp_database_url)
        try:
            # Duplicate email must fail
            with _pytest.raises(Exception, match="uq_users_email|unique"):
                with engine2.begin() as conn:
                    conn.execute(
                        _text(
                            "INSERT INTO ita.users (email, full_name, hashed_password) "
                            "VALUES (:e, :n, :p)"
                        ),
                        {"e": "alice@example.com", "n": "Bob", "p": "hash2"},
                    )

            # score out of range must fail
            with _pytest.raises(Exception, match="ck_assessments_score_range|check"):
                with engine2.begin() as conn:
                    conn.execute(
                        _text(
                            "INSERT INTO ita.assessments (user_id, type, score) "
                            "VALUES (:uid, :t, :s)"
                        ),
                        {"uid": user_id, "t": "java", "s": 150},
                    )

            # FK violation must fail
            with _pytest.raises(Exception, match="fk_|foreign key"):
                with engine2.begin() as conn:
                    conn.execute(
                        _text(
                            "INSERT INTO ita.assessments (user_id, type, score) "
                            "VALUES (:uid, :t, :s)"
                        ),
                        {"uid": 999999, "t": "java", "s": 50},
                    )
        finally:
            engine2.dispose()
    finally:
        engine.dispose()
