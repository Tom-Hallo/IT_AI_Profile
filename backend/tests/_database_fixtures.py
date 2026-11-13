from __future__ import annotations

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

BACKEND_DIR = Path(__file__).resolve().parents[1]

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
            encoding="utf-8",
            timeout=60,
            check=False,
        )

    return run


@pytest.fixture
def temp_database_url() -> Iterator[str]:
    """Create an isolated temporary PostgreSQL database for integration tests."""
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("RUN_INTEGRATION=1 is required")

    base_url = make_url(settings.database_url.get_secret_value())
    name = f"ita_migration_test_{uuid.uuid4().hex[:10]}"

    admin = create_engine(
        base_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    created = False

    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True

        yield base_url.set(database=name).render_as_string(hide_password=False)
    finally:
        try:
            if created:
                with admin.connect() as connection:
                    connection.execute(
                        text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
                    )
        finally:
            admin.dispose()
