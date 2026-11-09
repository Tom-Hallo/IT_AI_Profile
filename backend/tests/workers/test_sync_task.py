"""Tests for GitHub sync worker background task."""

from unittest.mock import MagicMock, patch

import pytest

import app.modules.assessments.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.cvs.models  # noqa: F401
import app.modules.github.models  # noqa: F401
import app.modules.roadmaps.models  # noqa: F401
import app.modules.users.models  # noqa: F401
from app.modules.users.models import User
from app.workers.tasks.sync_repositories import sync_user_repositories_task


def test_invalid_user_id_raises_value_error():
    with pytest.raises(ValueError, match="user_id không hợp lệ"):
        sync_user_repositories_task(0)

    with pytest.raises(ValueError, match="user_id không hợp lệ"):
        sync_user_repositories_task(-1)


def test_user_not_found_raises_value_error():
    mock_db = MagicMock()
    mock_db.scalar.return_value = None

    with patch("app.workers.tasks.sync_repositories.session_scope") as mock_scope:
        mock_scope.return_value.__enter__.return_value = mock_db
        with pytest.raises(ValueError, match="Không tìm thấy người dùng"):
            sync_user_repositories_task(999)


def test_sync_user_task_success():
    fake_user = User(
        id=10,
        email="dev@example.com",
        full_name="Dev User",
        hashed_password=None,
    )
    mock_db = MagicMock()
    mock_db.scalar.return_value = fake_user

    async def fake_sync(db, user):
        return {
            "status": "completed",
            "synced_count": 3,
            "last_synced_at": "2026-11-08T15:00:00Z",
        }

    with (
        patch("app.workers.tasks.sync_repositories.session_scope") as mock_scope,
        patch(
            "app.workers.tasks.sync_repositories.sync_repositories_for_user",
            side_effect=fake_sync,
        ),
    ):
        mock_scope.return_value.__enter__.return_value = mock_db

        result = sync_user_repositories_task(10)
        assert result["user_id"] == 10
        assert result["status"] == "completed"
        assert result["synced_count"] == 3
        assert result["last_synced_at"] == "2026-11-08T15:00:00Z"
