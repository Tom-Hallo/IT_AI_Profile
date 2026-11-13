"""Regression tests for SQLAlchemy mapper initialization and GitHub OAuth."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import init_models
from app.modules.auth import router as auth_router
from app.modules.auth.github import GitHubIdentity
from app.modules.auth.service import get_or_create_github_user
from app.modules.users.models import User

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _subprocess_test_env() -> dict[str, str]:
    """Provide safe configuration for subprocess import tests."""
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": "postgresql+psycopg://test:test@127.0.0.1:1/ita_mapper_test",
            "REDIS_URL": "redis://127.0.0.1:1/0",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )
    return env


def test_fresh_python_process_session_import_configures_all_mappers():
    """Verify session imports configure all ORM mappers."""
    code = (
        "import sys; "
        "sys.path.insert(0, '.'); "
        "import app.db.session; "
        "import app.modules.github.models; "
        "from app.modules.users.models import User; "
        "from sqlalchemy.orm import configure_mappers; "
        "configure_mappers(); "
        "print('SESSION_MAPPERS_OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        env=_subprocess_test_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, f"Session mapper config failed: {result.stderr}"
    assert "SESSION_MAPPERS_OK" in result.stdout


def test_worker_task_module_can_query_user_without_mapper_error():
    """Verify worker imports configure ORM relationships."""
    code = (
        "import sys; "
        "sys.path.insert(0, '.'); "
        "import app.workers.tasks.sync_repositories; "
        "from app.modules.users.models import User; "
        "from sqlalchemy.orm import configure_mappers; "
        "configure_mappers(); "
        "print('WORKER_MAPPERS_OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        env=_subprocess_test_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, f"Worker mapper config failed: {result.stderr}"
    assert "WORKER_MAPPERS_OK" in result.stdout


@pytest.fixture
def isolated_db_session():
    """Create an isolated SQLite database session for testing."""
    init_models()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def do_attach(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS ita;")
        cursor.close()

    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS ita.users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(255) NOT NULL UNIQUE,
                full_name VARCHAR(255) NOT NULL,
                hashed_password VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS ita.user_oauth_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL,
                provider_user_id VARCHAR(255) NOT NULL,
                encrypted_access_token TEXT,
                scope VARCHAR(255),
                access_mode VARCHAR(20) NOT NULL DEFAULT 'public_only',
                token_updated_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_user_oauth_accounts_provider_provider_user_id
                    UNIQUE (provider, provider_user_id)            );
            """
        )

    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_get_or_create_github_user_with_isolated_db(isolated_db_session: Session):
    """Verify GitHub user creation and retrieval without mapper errors."""
    identity = GitHubIdentity(
        provider_user_id="gh-987654",
        email="developer@example.com",
        full_name="GitHub Developer",
        access_token="gho_test_token_12345",
    )

    # 1. Create new user via OAuth
    created_user = get_or_create_github_user(isolated_db_session, identity)
    isolated_db_session.commit()

    assert created_user.id is not None
    assert created_user.email == "developer@example.com"
    assert created_user.full_name == "GitHub Developer"

    # Verify relationships are configured on the User mapper
    user_mapper = User.__mapper__
    assert "assessments" in user_mapper.relationships
    assert "cvs" in user_mapper.relationships
    assert "roadmaps" in user_mapper.relationships
    assert "repositories" in user_mapper.relationships
    assert "oauth_accounts" in user_mapper.relationships

    # 2. Re-login with the same GitHub identity should return existing user
    relogin_user = get_or_create_github_user(isolated_db_session, identity)
    assert relogin_user.id == created_user.id
    assert relogin_user.email == created_user.email


def test_oauth_callback_and_auth_me_integration(
    isolated_db_session: Session, monkeypatch
):
    """End-to-end integration test: OAuth callback -> session -> /api/v1/auth/me."""
    fake_settings = SimpleNamespace(
        app_env="test",
        frontend_url="http://localhost:5173",
        cors_origins=["http://localhost:5173"],
        github_oauth_enabled=True,
        github_client_id="test-client-id",
        github_redirect_uri="http://localhost:8000/api/v1/auth/github/callback",
    )
    monkeypatch.setattr(auth_router, "settings", fake_settings)

    # In-memory Redis simulation for session storage
    redis_store: dict[str, str] = {}
    mock_redis = MagicMock()
    mock_redis.set.side_effect = lambda k, v, ex=None: redis_store.__setitem__(
        k, str(v)
    )
    mock_redis.get.side_effect = lambda k: (
        redis_store.get(k, "").encode() if k in redis_store else None
    )
    mock_redis.getdel.side_effect = lambda k: (
        redis_store.pop(k).encode() if k in redis_store else None
    )

    monkeypatch.setattr("app.modules.auth.service._get_redis", lambda: mock_redis)
    monkeypatch.setattr(
        "app.modules.auth.router.consume_oauth_state", lambda s, b: True
    )

    async def fake_identity(code):
        return GitHubIdentity(
            provider_user_id="gh-456789",
            email="oauth.user@example.com",
            full_name="OAuth Authenticated User",
            access_token="gho_valid_token_xyz",
        )

    monkeypatch.setattr(auth_router, "get_github_identity", fake_identity)

    # Use FastAPI with router and dependency override for get_session
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1")
    app.dependency_overrides[auth_router.get_session] = lambda: isolated_db_session

    client = TestClient(app)

    # Set initial OAuth cookies
    client.cookies.set(
        auth_router.OAUTH_STATE_COOKIE, "valid-state", path="/api/v1/auth"
    )
    client.cookies.set(
        auth_router.OAUTH_BROWSER_COOKIE, "browser-binding", path="/api/v1/auth"
    )

    # Call OAuth callback endpoint (real get_or_create_github_user is executed!)
    response = client.get(
        "/api/v1/auth/github/callback?code=fake-oauth-code&state=valid-state",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/"
    assert auth_router.SESSION_COOKIE in response.cookies
    session_id = response.cookies[auth_router.SESSION_COOKIE]
    assert session_id is not None

    # Verify user exists in DB
    db_user = isolated_db_session.scalar(
        select(User).where(User.email == "oauth.user@example.com")
    )
    assert db_user is not None
    assert db_user.full_name == "OAuth Authenticated User"

    # Call /api/v1/auth/me with the session cookie
    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["id"] == db_user.id
    assert me_data["email"] == "oauth.user@example.com"
    assert me_data["full_name"] == "OAuth Authenticated User"
    assert "hashed_password" not in me_data
