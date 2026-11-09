from types import SimpleNamespace
from unittest.mock import MagicMock
from importlib import import_module

from sqlalchemy.orm import configure_mappers

import pytest
from sqlalchemy.orm import configure_mappers
import app.modules.assessments.models as assessment_models
import app.modules.auth.models as auth_models
import app.modules.cvs.models as cv_models
import app.modules.github.models as github_models
import app.modules.roadmaps.models as roadmap_models
from app.modules.auth.github import GitHubIdentity
from app.modules.auth.models import OAuthAccount
from app.modules.auth.service import (
    GitHubAccountConflictError,
    get_or_create_github_user,
)
from app.modules.users.models import User

assert all(
    (
        assessment_models,
        auth_models,
        cv_models,
        github_models,
        roadmap_models,
    )
)
MODEL_MODULES = (
    "app.modules.users.models",
    "app.modules.auth.models",
    "app.modules.roadmaps.models",
    "app.modules.github.models",
    "app.modules.cvs.models",
    "app.modules.assessments.models",
)

for module_path in MODEL_MODULES:
    import_module(module_path)

configure_mappers()


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def identity():
    return GitHubIdentity(
        provider_user_id="123456",
        email="TEST@EXAMPLE.COM",
        full_name="Test User",
    )


def test_return_existing_github_user(db, identity):
    existing_user = User(
        id=1,
        email="test@example.com",
        full_name="Test User",
        hashed_password=None,
    )

    oauth_account = SimpleNamespace(user=existing_user)

    db.execute.return_value.scalar_one_or_none.return_value = oauth_account

    result = get_or_create_github_user(db, identity)

    assert result is existing_user
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_reject_existing_email(db, identity):
    db.execute.return_value.scalar_one_or_none.side_effect = [
        None,
        User(
            id=1,
            email="test@example.com",
            full_name="Existing User",
            hashed_password="hashed-password",
        ),
    ]

    with pytest.raises(GitHubAccountConflictError):
        get_or_create_github_user(db, identity)

    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_create_new_github_user(db, identity):
    def fake_flush():
        # Giả lập database tự sinh User ID.
        db.add.call_args_list[0].args[0].id = 10

    db.execute.return_value.scalar_one_or_none.side_effect = [
        None,
        None,
    ]
    db.flush.side_effect = fake_flush

    result = get_or_create_github_user(db, identity)

    assert result.email == "test@example.com"
    assert result.full_name == "Test User"
    assert result.hashed_password is None

    assert db.add.call_count == 2

    created_user = db.add.call_args_list[0].args[0]
    created_oauth = db.add.call_args_list[1].args[0]

    assert isinstance(created_user, User)
    assert isinstance(created_oauth, OAuthAccount)
    assert created_oauth.user_id == 10
    assert created_oauth.provider == "github"
    assert created_oauth.provider_user_id == "123456"

    db.commit.assert_called_once()


def test_reject_invalid_identity(db):
    invalid_identity = GitHubIdentity(
        provider_user_id="",
        email="test@example.com",
        full_name="Test User",
    )

    with pytest.raises(ValueError):
        get_or_create_github_user(db, invalid_identity)

    db.execute.assert_not_called()
    db.add.assert_not_called()
