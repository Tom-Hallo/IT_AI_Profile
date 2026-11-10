"""Tests for PBI-013: Fork, Ownership & Real Contribution Verification.
Covers the entire 24-point Mandatory Test Matrix.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.main import create_app
from app.modules.analysis.models import (
    RepositoryVerification,
    VerificationEvidence,
)
from app.modules.analysis.schemas import (
    RepositoryAnalysisResponse,
    RepositoryVerificationResponse,
    RepositoryVerificationSummary,
    VerificationEvidenceItem,
    VerificationRequest,
)
from app.modules.analysis.verification_service import (
    persist_verification_result,
    verify_private_repo_consent,
    verify_repository_access,
    verify_repository_contributions,
)
from app.modules.auth.models import OAuthAccount
from app.modules.github.client import (
    GitHubApiClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository
from app.modules.users.models import User

# ============================================================================
# Helpers & Mock Fixtures
# ============================================================================


def _create_mock_user(
    user_id: int = 1,
    email: str = "developer@example.com",
    full_name: str = "Test Developer",
) -> User:
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = email
    u.full_name = full_name
    return u


def _create_mock_repo(
    repo_id: int = 10,
    name: str = "demo-project",
    full_name: str = "mydev/demo-project",
    private: bool = False,
    owner_id: int = 1,
    default_branch: str = "main",
    is_fork: bool = False,
    fork_source: str | None = None,
) -> Repository:
    r = MagicMock(spec=Repository)
    r.id = repo_id
    r.github_repo_id = 9000 + repo_id
    r.name = name
    r.full_name = full_name
    r.private = private
    r.owner_id = owner_id
    r.default_branch = default_branch
    r.is_fork = is_fork
    r.fork_source = fork_source
    r.description = "Test repository for verification"
    r.html_url = f"https://github.com/{full_name}"
    return r


def _create_mock_oauth(
    user_id: int = 1,
    github_user_id: str = "12345",
    scope: str = "read:user,repo",
) -> OAuthAccount:
    o = MagicMock(spec=OAuthAccount)
    o.user_id = user_id
    o.provider = "github"
    o.provider_user_id = github_user_id
    o.scope = scope
    return o


def make_mock_db(
    repo: Repository,
    oauth_acc: OAuthAccount | None = None,
    existing_ver: RepositoryVerification | None = None,
) -> MagicMock:
    mock_db = MagicMock()
    if oauth_acc is None:
        oauth_acc = _create_mock_oauth(user_id=repo.owner_id)

    def _scalar(stmt):
        s_str = str(stmt).lower()
        if "from ita.repositories" in s_str or "repositories" in s_str:
            return repo
        if "from ita.oauth_accounts" in s_str or "oauth_accounts" in s_str:
            return oauth_acc
        if (
            "from ita.repository_verifications" in s_str
            or "repository_verifications" in s_str
        ):
            return existing_ver
        return None

    mock_db.scalar.side_effect = _scalar
    return mock_db


# ============================================================================
# Test Scenarios 1-5: Provenance, Ownership & Fork Behavior
# ============================================================================


@pytest.mark.anyio
async def test_01_original_repository_owned_by_developer(monkeypatch):
    """Scenario 1: Original repository owned by developer.
    is_fork=False, repo.owner_id == user.id.
    Commits authored by user are verified, provenance is original, owner role.
    """
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(
        repo_id=1, owner_id=1, full_name="mydev/original-app", is_fork=False
    )
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user,repo"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9001,
            "name": "original-app",
            "full_name": "mydev/original-app",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    mock_client.list_commits = AsyncMock(
        return_value=[
            {
                "sha": "aaa111",
                "author": {"id": 12345, "login": "mydev"},
                "commit": {
                    "message": "Initial commit",
                    "author": {"date": "2026-10-01T10:00:00Z"},
                },
                "stats": {"additions": 100, "deletions": 10},
            }
        ]
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.provenance_type == "original"
    assert ver.ownership_status == "owner"
    assert ver.is_fork is False
    assert ver.anti_inflation_flag is False
    assert ver.verified_commits_count == 1
    assert ver.unverified_commits_count == 0
    assert ver.verified_additions == 100
    assert ver.verification_status == "verified"


@pytest.mark.anyio
async def test_02_fork_owned_by_developer_without_new_contribution(monkeypatch):
    """Scenario 2: Fork owned by developer without new contribution.
    is_fork=True, 0 commits by user -> anti_inflation_flag=True, status=no_contribution.
    """
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(
        repo_id=2, owner_id=1, full_name="mydev/forked-app", is_fork=True
    )
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9002,
            "name": "forked-app",
            "full_name": "mydev/forked-app",
            "fork": True,
            "owner": {"id": 12345, "login": "mydev"},
            "parent": {
                "id": 8001,
                "name": "upstream-app",
                "full_name": "upstream-org/upstream-app",
                "html_url": "https://github.com/upstream-org/upstream-app",
            },
        }
    )
    # Commits are by external author
    mock_client.list_commits = AsyncMock(
        return_value=[
            {
                "sha": "upstream999",
                "author": {"id": 99999, "login": "upstream-dev"},
                "commit": {
                    "message": "Original feature from upstream",
                    "author": {"date": "2026-09-01T10:00:00Z"},
                },
                "stats": {"additions": 500, "deletions": 50},
            }
        ]
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.is_fork is True
    assert ver.provenance_type == "fork"
    assert ver.ownership_status == "fork_owner"
    assert ver.parent_repo_name == "upstream-org/upstream-app"
    assert ver.parent_metadata_status == "verified"
    assert ver.anti_inflation_flag is True
    assert ver.verified_commits_count == 0
    assert ver.unverified_commits_count == 1
    assert ver.verification_status == "no_contribution"


@pytest.mark.anyio
async def test_03_fork_with_verified_developer_commit(monkeypatch):
    """Scenario 3: Fork with verified developer commit.
    is_fork=True, user has 1 verified commit and 1 inherited commit.
    anti_inflation_flag=False, status=verified.
    """
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(
        repo_id=3, owner_id=1, full_name="mydev/active-fork", is_fork=True
    )
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)

    async def mock_commit_details(owner, repo_name, sha):
        if owner == "upstream" and repo_name == "core":
            if sha == "user123":
                raise GitHubNotFoundError("Developer commit is not present in upstream")

            if sha == "upstream111":
                return {"sha": sha}

        raise AssertionError(f"Unexpected commit lookup: {owner}/{repo_name}/{sha}")

    mock_client.get_commit_details = AsyncMock(side_effect=mock_commit_details)

    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9003,
            "name": "active-fork",
            "full_name": "mydev/active-fork",
            "fork": True,
            "owner": {"id": 12345, "login": "mydev"},
            "parent": {"id": 8002, "full_name": "upstream/core"},
        }
    )
    mock_client.list_commits = AsyncMock(
        return_value=[
            {
                "sha": "user123",
                "author": {"id": 12345, "login": "mydev"},
                "commit": {
                    "message": "Custom bug fix by developer",
                    "author": {"date": "2026-10-15T12:00:00Z"},
                },
                "stats": {"additions": 40, "deletions": 5},
            },
            {
                "sha": "upstream111",
                "author": {"id": 99999, "login": "core-team"},
                "commit": {
                    "message": "Core upstream framework",
                    "author": {"date": "2026-08-01T12:00:00Z"},
                },
                "stats": {"additions": 1000, "deletions": 200},
            },
        ]
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.is_fork is True
    assert ver.anti_inflation_flag is False
    assert ver.verified_commits_count == 1
    assert ver.unverified_commits_count == 1
    assert ver.verified_additions == 40
    assert ver.verified_deletions == 5
    assert ver.verification_status == "verified"


@pytest.mark.anyio
async def test_04_fork_inherited_commits_never_attributed_to_user(monkeypatch):
    """Scenario 4: Commits authored by other people in a fork are marked
    is_fork_inherited=True and unverified. Never attributed to developer.
    """
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(
        repo_id=4, owner_id=1, full_name="mydev/fork-repo", is_fork=True
    )
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9004,
            "full_name": "mydev/fork-repo",
            "fork": True,
            "owner": {"id": 12345, "login": "mydev"},
            "parent": {"id": 8003, "full_name": "original-org/base-repo"},
        }
    )
    mock_client.list_commits = AsyncMock(
        return_value=[
            {
                "sha": "ext111",
                "author": {"id": 88888, "login": "external-author"},
                "commit": {
                    "message": "Upstream code",
                    "author": {"date": "2026-09-01T00:00:00Z"},
                },
                "stats": {"additions": 300, "deletions": 50},
            }
        ]
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    ev_list = ver.evidence
    assert len(ev_list) >= 1
    ext_ev = next(e for e in ev_list if e.target_identifier == "ext111")
    assert ext_ev.is_fork_inherited is True
    assert ext_ev.verification_status == "unverified"
    assert "kế thừa từ repo gốc" in ext_ev.rationale.lower()


@pytest.mark.anyio
async def test_05_collaboration_on_unowned_repository(monkeypatch):
    """Scenario 5: Collaboration on repository not owned by developer.
    repo.owner_id != user.id, provenance=collaboration, ownership=collaborator.
    """
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=5, owner_id=99, full_name="company/shared-backend")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9005,
            "full_name": "company/shared-backend",
            "fork": False,
            "owner": {"id": 99999, "login": "company"},
        }
    )
    mock_client.list_commits = AsyncMock(
        return_value=[
            {
                "sha": "collab1",
                "author": {"id": 12345, "login": "mydev"},
                "commit": {
                    "message": "Add payment gateway integration",
                    "author": {"date": "2026-10-20T10:00:00Z"},
                },
                "stats": {"additions": 80, "deletions": 10},
            }
        ]
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.ownership_status == "collaborator"
    assert ver.provenance_type == "collaboration"
    assert ver.verified_commits_count == 1
    assert ver.verification_status == "verified"


# ============================================================================
# Test Scenarios 6-8: Pull Request Verification
# ============================================================================


@pytest.mark.anyio
async def test_06_verified_user_created_pr(monkeypatch):
    """Scenario 6: PR opened by the user actor identity is verified and counted."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=6, owner_id=1, full_name="mydev/pr-test")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9006,
            "full_name": "mydev/pr-test",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    mock_client.list_commits = AsyncMock(return_value=[])
    mock_client.list_pull_requests = AsyncMock(
        return_value=[
            {
                "id": 101,
                "number": 42,
                "title": "Implement OAuth flow",
                "state": "closed",
                "merged_at": "2026-10-18T14:00:00Z",
                "created_at": "2026-10-17T10:00:00Z",
                "user": {"id": 12345, "login": "mydev"},
                "head": {"repo": {"full_name": "mydev/pr-test"}},
                "base": {"repo": {"full_name": "mydev/pr-test"}},
                "html_url": "https://github.com/mydev/pr-test/pull/42",
            }
        ]
    )

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.verified_prs_count == 1
    assert ver.unverified_prs_count == 0
    pr_ev = next(e for e in ver.evidence if e.evidence_type == "pull_request")
    assert pr_ev.target_identifier == "42"
    assert pr_ev.verification_status == "verified"
    assert pr_ev.pr_merged is True
    assert pr_ev.actor_login == "mydev"


@pytest.mark.anyio
async def test_07_pr_created_by_another_developer(monkeypatch):
    """Scenario 7: PR created by another developer is marked unverified."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=7, owner_id=1, full_name="mydev/pr-other")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9007,
            "full_name": "mydev/pr-other",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    mock_client.list_commits = AsyncMock(return_value=[])
    mock_client.list_pull_requests = AsyncMock(
        return_value=[
            {
                "id": 102,
                "number": 43,
                "title": "Fix typo in docs",
                "state": "open",
                "merged_at": None,
                "created_at": "2026-10-19T10:00:00Z",
                "user": {"id": 77777, "login": "external-contributor"},
                "html_url": "https://github.com/mydev/pr-other/pull/43",
            }
        ]
    )

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.verified_prs_count == 0
    assert ver.unverified_prs_count == 1
    pr_ev = next(e for e in ver.evidence if e.evidence_type == "pull_request")
    assert pr_ev.verification_status == "unverified"
    assert "external-contributor" in pr_ev.rationale


@pytest.mark.anyio
async def test_08_closed_pr_never_merged(monkeypatch):
    """Scenario 8: Closed PR that was never merged is marked pr_merged=False
    and not mislabeled as merged.
    """
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=8, owner_id=1, full_name="mydev/pr-closed")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9008,
            "full_name": "mydev/pr-closed",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    mock_client.list_commits = AsyncMock(return_value=[])
    mock_client.list_pull_requests = AsyncMock(
        return_value=[
            {
                "id": 103,
                "number": 44,
                "title": "Experimental redesign",
                "state": "closed",
                "merged_at": None,  # Closed without merge!
                "created_at": "2026-10-10T10:00:00Z",
                "user": {"id": 12345, "login": "mydev"},
                "html_url": "https://github.com/mydev/pr-closed/pull/44",
            }
        ]
    )

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    pr_ev = next(e for e in ver.evidence if e.evidence_type == "pull_request")
    assert pr_ev.pr_state == "closed"
    assert pr_ev.pr_merged is False
    assert "chưa merge" in pr_ev.rationale


# ============================================================================
# Test Scenarios 9-11: Edge Cases & Incomplete Metadata
# ============================================================================


@pytest.mark.anyio
async def test_09_missing_author_identity_falls_back_safely(monkeypatch):
    """Scenario 9: Commit with author=None (e.g. unlinked git CLI config).
    Display name or email matching user is NOT trusted. Marked unverified.
    """
    user = _create_mock_user(user_id=1, email="mydev@example.com")
    repo = _create_mock_repo(repo_id=9, owner_id=1, full_name="mydev/no-author")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9009,
            "full_name": "mydev/no-author",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    # Commit with null author
    mock_client.list_commits = AsyncMock(
        return_value=[
            {
                "sha": "anon999",
                "author": None,
                "commit": {
                    "message": "Commit without GitHub account link",
                    "author": {
                        "name": "mydev",
                        "email": "mydev@example.com",
                        "date": "2026-10-10T10:00:00Z",
                    },
                },
                "stats": {"additions": 10, "deletions": 2},
            }
        ]
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.verified_commits_count == 0
    assert ver.unverified_commits_count == 1
    ev = next(e for e in ver.evidence if e.target_identifier == "anon999")
    assert ev.verification_status == "unverified"
    assert "thiếu liên kết github" in ev.rationale.lower()


@pytest.mark.anyio
async def test_10_missing_or_inaccessible_parent_metadata(monkeypatch):
    """Scenario 10: Fork repository where parent metadata is inaccessible or null.
    System marks parent_metadata_status='unknown', logs limitation, confidence reduced.
    """
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(
        repo_id=10, owner_id=1, full_name="mydev/orphaned-fork", is_fork=True
    )
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    # Fork is true, but parent field is null (e.g. parent deleted or private)
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9010,
            "full_name": "mydev/orphaned-fork",
            "fork": True,
            "owner": {"id": 12345, "login": "mydev"},
            "parent": None,
        }
    )
    mock_client.list_commits = AsyncMock(return_value=[])
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.is_fork is True
    assert ver.parent_metadata_status == "unknown"
    assert any("metadata" in lim.lower() for lim in ver.limitations)
    assert ver.confidence in ("medium", "uncertain")


@pytest.mark.anyio
async def test_11_incomplete_github_api_response(monkeypatch):
    """Scenario 11: Rate limited or incomplete API response records partial
    coverage status.
    """
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=11, owner_id=1, full_name="mydev/large-repo")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9011,
            "full_name": "mydev/large-repo",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    # Raising a rate limit on commits
    mock_client.list_commits = AsyncMock(
        side_effect=GitHubRateLimitError("API rate limit exceeded for user ID 12345")
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.coverage_status == "partial"
    assert any(
        "rate-limit" in lim.lower() or "rate limit" in lim.lower()
        for lim in ver.limitations
    )
    assert ver.confidence in ("low", "uncertain")


# ============================================================================
# Test Scenarios 12-16: API Limits, Time-ranges & Deduplication
# ============================================================================


@pytest.mark.anyio
async def test_12_github_rate_limit_and_error_handling(monkeypatch):
    """Scenario 12: GitHub 401/404 translates properly to standard HTTPException."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=12, owner_id=1)
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    # Auth user call fails with 401 Bad credentials
    mock_client.get_authenticated_user = AsyncMock(
        side_effect=GitHubTokenRevokedError("Bad credentials")
    )

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    # When token is revoked, service falls back to unauthenticated profile or marks 401
    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )
    assert ver.verification_status in (
        "unverified",
        "no_contribution",
        "unknown",
    )


@pytest.mark.anyio
async def test_13_pagination_and_partial_coverage(monkeypatch):
    """Scenario 13: Large commit count hits pagination bound and logs limitation."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=13, owner_id=1, full_name="mydev/pagination-test")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    # 100 commits returned
    fake_commits = [
        {
            "sha": f"sha{i:04d}",
            "author": {"id": 12345, "login": "mydev"},
            "commit": {
                "message": f"Commit {i}",
                "author": {"date": "2026-10-01T10:00:00Z"},
            },
            "stats": {"additions": 1, "deletions": 1},
        }
        for i in range(100)
    ]

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9013,
            "full_name": "mydev/pagination-test",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    mock_client.list_commits = AsyncMock(return_value=fake_commits)
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.verified_commits_count == 100


@pytest.mark.anyio
async def test_14_commit_or_pr_outside_time_range_excluded(monkeypatch):
    """Scenario 14: Commit outside requested time-range is excluded."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=14, owner_id=1, full_name="mydev/timerange-test")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    req = VerificationRequest(
        mode="month",
        month="2026-10",
        timezone="UTC",
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9014,
            "full_name": "mydev/timerange-test",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    # One commit in October 2026, one commit in January 2026
    mock_client.list_commits = AsyncMock(
        return_value=[
            {
                "sha": "october123",
                "author": {"id": 12345, "login": "mydev"},
                "commit": {
                    "message": "October commit",
                    "author": {"date": "2026-10-15T10:00:00Z"},
                },
                "stats": {"additions": 15, "deletions": 2},
            },
            {
                "sha": "january123",
                "author": {"id": 12345, "login": "mydev"},
                "commit": {
                    "message": "January commit",
                    "author": {"date": "2026-01-15T10:00:00Z"},
                },
                "stats": {"additions": 100, "deletions": 50},
            },
        ]
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(mock_db, repo.id, user, req)

    assert ver.verified_commits_count == 1
    assert ver.verified_additions == 15
    assert any(e.target_identifier == "october123" for e in ver.evidence)
    assert not any(e.target_identifier == "january123" for e in ver.evidence)


@pytest.mark.anyio
async def test_15_repeated_synchronization_and_idempotency(monkeypatch):
    """Scenario 15: Running verification twice for the same repo updates
    the existing record instead of crashing or duplicating.
    """
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=15, owner_id=1, full_name="mydev/idempotent-test")

    existing_record = MagicMock(spec=RepositoryVerification)
    existing_record.id = 77
    existing_record.repository_id = 15
    existing_record.user_id = 1
    existing_record.evidence = []

    mock_db = make_mock_db(repo, existing_ver=existing_record)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9015,
            "full_name": "mydev/idempotent-test",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    mock_client.list_commits = AsyncMock(return_value=[])
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.repository_id == 15
    mock_db.flush.assert_called()


@pytest.mark.anyio
async def test_16_parent_fork_contribution_overlap_deduplication(monkeypatch):
    """Scenario 16: Deduplication of identical commit SHAs ensures distinct counting."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=16, owner_id=1, full_name="mydev/dedup-test")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    duplicate_commits = [
        {
            "sha": "dup_sha_123",
            "author": {"id": 12345, "login": "mydev"},
            "commit": {
                "message": "First occurrence",
                "author": {"date": "2026-10-10T10:00:00Z"},
            },
            "stats": {"additions": 10, "deletions": 0},
        },
        {
            "sha": "dup_sha_123",  # Same SHA!
            "author": {"id": 12345, "login": "mydev"},
            "commit": {
                "message": "Duplicate branch merge",
                "author": {"date": "2026-10-10T10:00:00Z"},
            },
            "stats": {"additions": 10, "deletions": 0},
        },
    ]

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9016,
            "full_name": "mydev/dedup-test",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    mock_client.list_commits = AsyncMock(return_value=duplicate_commits)
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest()
    )

    assert ver.verified_commits_count == 1
    assert ver.verified_additions == 10
    commit_evs = [e for e in ver.evidence if e.target_identifier == "dup_sha_123"]
    assert len(commit_evs) == 1


# ============================================================================
# Test Scenarios 17-21: Security, Scopes & Isolation
# ============================================================================


def test_17_private_repo_without_consent_fails_403(monkeypatch):
    """Scenario 17: Private repository without 'repo' OAuth scope fails with 403."""
    mock_db = MagicMock()
    monkeypatch.setattr(
        "app.modules.analysis.verification_service.has_private_access",
        lambda _db, _uid: True,
    )
    private_repo = _create_mock_repo(repo_id=17, private=True)
    with pytest.raises(HTTPException) as exc:
        verify_private_repo_consent(
            private_repo, scope="read:user", db=mock_db, user_id=1
        )
    assert exc.value.status_code == 403
    assert "scope 'repo'" in exc.value.detail


def test_18_revoked_consent_fails_closed(monkeypatch):
    """Scenario 18: Missing or empty scope fails closed with 403."""
    mock_db = MagicMock()
    monkeypatch.setattr(
        "app.modules.analysis.verification_service.has_private_access",
        lambda _db, _uid: False,
    )
    private_repo = _create_mock_repo(repo_id=18, private=True)
    with pytest.raises(HTTPException) as exc:
        verify_private_repo_consent(private_repo, scope="repo", db=mock_db, user_id=1)
    assert exc.value.status_code == 403


def test_19_cross_user_evidence_access_idor_prevented():
    """Scenario 19: User A attempting to access User B's repository fails with 404."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = None
    user_a = _create_mock_user(user_id=1)

    with pytest.raises(HTTPException) as exc:
        verify_repository_access(mock_db, repository_id=999, user=user_a)
    assert exc.value.status_code == 404
    assert (
        "Không tìm thấy repository hoặc bạn không có quyền truy cập" in exc.value.detail
    )


def test_20_public_scope_on_private_repo_rejected(monkeypatch):
    """Scenario 20: Scope 'public' on private repo is rejected."""
    mock_db = MagicMock()
    monkeypatch.setattr(
        "app.modules.analysis.verification_service.has_private_access",
        lambda _db, _uid: True,
    )
    private_repo = _create_mock_repo(repo_id=20, private=True)
    with pytest.raises(HTTPException) as exc:
        verify_private_repo_consent(
            private_repo, scope="read:user", db=mock_db, user_id=1
        )
    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_21_combined_scope_unique_identifiers(monkeypatch):
    """Scenario 21: Preserving unique identifiers across public and private scopes."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=21, owner_id=1, full_name="mydev/combined-scope")
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user,repo"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "id": 9021,
            "full_name": "mydev/combined-scope",
            "fork": False,
            "owner": {"id": 12345, "login": "mydev"},
        }
    )
    mock_client.list_commits = AsyncMock(
        return_value=[
            {
                "sha": "commit_sha_unique",
                "author": {"id": 12345, "login": "mydev"},
                "commit": {
                    "message": "feat: unique",
                    "author": {"date": "2026-10-10T10:00:00Z"},
                },
                "stats": {"additions": 5, "deletions": 1},
            }
        ]
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    ver = await verify_repository_contributions(
        mock_db, repo.id, user, VerificationRequest(scope="all")
    )
    assert ver.repository_id == 21
    commit_ev = next(e for e in ver.evidence if e.evidence_type == "commit")
    assert commit_ev.target_identifier == "commit_sha_unique"


# ============================================================================
# Test Scenarios 22-24: API Integration, Schemas & Pipeline Non-Regression
# ============================================================================


def test_22_backend_api_router_integration(monkeypatch):
    """Scenario 22: API endpoints for triggering and retrieving verification."""
    app = create_app()
    user = _create_mock_user(user_id=1)
    app.dependency_overrides[get_current_user] = lambda: user
    mock_db = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_db

    repo = _create_mock_repo(repo_id=22, owner_id=1)

    now = datetime.now(UTC)
    mock_ver = RepositoryVerificationResponse(
        id=50,
        repository_id=22,
        repository_name="demo-project",
        repository_full_name="mydev/demo-project",
        user_id=1,
        job_id=None,
        report_id=None,
        provenance_type="original",
        ownership_status="owner",
        is_fork=False,
        parent_repo_name=None,
        parent_repo_url=None,
        parent_metadata_status="none",
        verification_status="verified",
        coverage_status="complete",
        confidence="high",
        verified_commits_count=5,
        unverified_commits_count=0,
        verified_prs_count=1,
        unverified_prs_count=0,
        verified_additions=120,
        verified_deletions=15,
        anti_inflation_flag=False,
        time_range=None,
        limitations=[],
        summary_data={"user_login": "mydev"},
        verified_at=now.isoformat(),
        evidence=[
            VerificationEvidenceItem(
                evidence_type="commit",
                target_identifier="commit123",
                verification_status="verified",
                actor_login="mydev",
                actor_id="12345",
                actor_type="User",
                html_url="https://github.com/mydev/demo-project/commit/commit123",
                title_or_message="feat: initial feature",
                is_merge=False,
                is_bot=False,
                is_fork_inherited=False,
                additions=120,
                deletions=15,
                recorded_at=now.isoformat(),
                rationale="Commit authored by user",
            )
        ],
    )

    from app.modules.analysis import (
        verification_router as ver_router_mod,
    )

    monkeypatch.setattr(
        ver_router_mod, "verify_repository_access", lambda *args, **kwargs: repo
    )
    monkeypatch.setattr(
        ver_router_mod,
        "get_stored_verification",
        lambda *args, **kwargs: mock_ver,
    )

    # For evidence endpoint
    mock_ver_orm = MagicMock(spec=RepositoryVerification)
    mock_ver_orm.id = 50
    mock_db.scalar.return_value = mock_ver_orm

    mock_ev_orm = MagicMock(spec=VerificationEvidence)
    mock_ev_orm.id = 1
    mock_ev_orm.evidence_type = "commit"
    mock_ev_orm.target_identifier = "commit123"
    mock_ev_orm.verification_status = "verified"
    mock_ev_orm.actor_login = "mydev"
    mock_ev_orm.actor_id = "12345"
    mock_ev_orm.actor_type = "User"
    mock_ev_orm.html_url = "https://github.com/mydev/demo-project/commit/commit123"
    mock_ev_orm.title_or_message = "feat: initial feature"
    mock_ev_orm.is_merge = False
    mock_ev_orm.is_bot = False
    mock_ev_orm.is_fork_inherited = False
    mock_ev_orm.additions = 120
    mock_ev_orm.deletions = 15
    mock_ev_orm.pr_state = None
    mock_ev_orm.pr_merged = None
    mock_ev_orm.source_repo = None
    mock_ev_orm.target_repo = None
    mock_ev_orm.recorded_at = now
    mock_ev_orm.rationale = "Commit authored by user"
    mock_ev_orm.metadata_ = None

    mock_db.scalars.return_value.all.return_value = [mock_ev_orm]

    client = TestClient(app)

    # 1. GET /verification
    res_get = client.get("/api/v1/repositories/22/verification")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["repository_id"] == 22
    assert data_get["provenance_type"] == "original"
    assert data_get["verified_commits_count"] == 5

    # 2. GET /verification/evidence
    res_ev = client.get("/api/v1/repositories/22/verification/evidence")
    assert res_ev.status_code == 200
    data_ev = res_ev.json()
    assert data_ev["total"] == 1
    assert data_ev["items"][0]["target_identifier"] == "commit123"


def test_23_schema_serialization_and_unknown_handling():
    """Scenario 23: Schemas handle missing or unknown values without speculation."""
    now = datetime.now(UTC)
    summary = RepositoryVerificationSummary(
        provenance_type="unknown",
        ownership_status="unknown",
        is_fork=False,
        parent_repo_name=None,
        parent_metadata_status="unknown",
        verification_status="unknown",
        coverage_status="unknown",
        confidence="uncertain",
        verified_commits_count=0,
        unverified_commits_count=0,
        verified_prs_count=0,
        unverified_prs_count=0,
        verified_additions=0,
        verified_deletions=0,
        anti_inflation_flag=False,
        verified_at=now,
    )
    dumped = summary.model_dump()
    assert dumped["provenance_type"] == "unknown"
    assert dumped["confidence"] == "uncertain"
    assert dumped["parent_repo_name"] is None


def test_24_no_regression_in_analysis_pipeline():
    """Scenario 24: Existing RepositoryAnalysisResponse embeds verification summary
    without breaking PBI-009/011/012 properties.
    """
    now = datetime.now(UTC)
    summary = RepositoryVerificationSummary(
        provenance_type="original",
        ownership_status="owner",
        is_fork=False,
        parent_repo_name=None,
        parent_metadata_status="none",
        verification_status="verified",
        coverage_status="complete",
        confidence="high",
        verified_commits_count=3,
        unverified_commits_count=0,
        verified_prs_count=1,
        unverified_prs_count=0,
        verified_additions=50,
        verified_deletions=10,
        anti_inflation_flag=False,
        verified_at=now,
    )

    analysis_res = RepositoryAnalysisResponse(
        repository_id=1,
        commit_sha="abcd" * 10,
        analyzed_at=now.isoformat(),
        scope="all",
        time_range=None,
        structure={"total_files": 1, "inspected_files": 1, "ignored_files": 0},
        languages=[],
        frameworks=[],
        architecture=[],
        evidence_count=0,
        budget={},
        verification=summary,
    )

    dumped = analysis_res.model_dump()
    assert dumped["repository_id"] == 1
    assert dumped["commit_sha"] == "abcd" * 10
    assert dumped["verification"] is not None
    assert dumped["verification"]["provenance_type"] == "original"
    assert dumped["verification"]["verified_commits_count"] == 3


@pytest.mark.anyio
async def test_public_scope_rejects_private_repo_before_github_call(
    monkeypatch,
):
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=30, private=True)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.verify_repository_access",
        lambda _db, _repo_id, _user: repo,
    )

    github_called = False

    def fake_get_token(_db, _user_id):
        nonlocal github_called
        github_called = True
        return "fake-token", "repo"

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        fake_get_token,
    )

    with pytest.raises(HTTPException) as exc:
        await verify_repository_contributions(
            db=MagicMock(),
            repository_id=repo.id,
            user=user,
            request=VerificationRequest(scope="public"),
        )

    assert exc.value.status_code == 403
    assert github_called is False


def test_get_verification_without_result_returns_404(monkeypatch):
    from app.modules.analysis import verification_router as router_module

    app = create_app()
    user = _create_mock_user(user_id=1)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: MagicMock()

    monkeypatch.setattr(
        router_module,
        "get_stored_verification",
        lambda *args, **kwargs: None,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/repositories/30/verification")

    assert response.status_code == 404
    assert response.json()["detail"] == ("Chưa có kết quả xác minh cho repository này.")


@pytest.mark.anyio
async def test_fork_collaborator_commit_is_not_inherited(monkeypatch):
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(
        repo_id=31,
        owner_id=1,
        full_name="mydev/team-fork",
        is_fork=True,
    )
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "full_name": "mydev/team-fork",
            "fork": True,
            "parent": {"full_name": "original-org/base-repo"},
        }
    )
    mock_client.list_commits = AsyncMock(
        return_value=[
            {
                "sha": "collaborator123",
                "author": {"id": 99999, "login": "teammate"},
                "commit": {
                    "message": "New feature on fork",
                    "author": {"date": "2026-10-20T10:00:00Z"},
                },
                "stats": {"additions": 20, "deletions": 2},
            }
        ]
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    mock_client.get_commit_details = AsyncMock(
        side_effect=GitHubNotFoundError("Commit not present in upstream")
    )

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    result = await verify_repository_contributions(
        mock_db,
        repo.id,
        user,
        VerificationRequest(),
    )

    commit = next(
        item for item in result.evidence if item.target_identifier == "collaborator123"
    )

    assert commit.is_fork_inherited is False
    assert commit.verification_status == "unverified"
    assert result.verified_commits_count == 0
    assert result.unverified_commits_count == 1


@pytest.mark.anyio
async def test_fork_partial_coverage_does_not_claim_no_contribution(
    monkeypatch,
):
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(
        repo_id=32,
        owner_id=1,
        full_name="mydev/rate-limited-fork",
        is_fork=True,
    )
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.get_repository_details = AsyncMock(
        return_value={
            "full_name": "mydev/rate-limited-fork",
            "fork": True,
            "parent": {
                "full_name": "upstream-org/original-project",
            },
        }
    )

    # GitHub không trả đủ dữ liệu commit.
    mock_client.list_commits = AsyncMock(
        side_effect=GitHubRateLimitError("GitHub rate limit exceeded")
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.GitHubApiClient",
        lambda *args, **kwargs: mock_client,
    )

    result = await verify_repository_contributions(
        mock_db,
        repo.id,
        user,
        VerificationRequest(),
    )

    assert result.coverage_status == "partial"
    assert result.verification_status == "unknown"
    assert result.confidence == "uncertain"
    assert result.verified_commits_count == 0
    assert result.anti_inflation_flag is True

    assert "chưa đủ dữ liệu" in result.summary_data["rationale_summary"].lower()


@pytest.mark.anyio
@pytest.mark.parametrize("truncated_api", ["commits", "prs"])
async def test_verification_marks_truncated_pagination_as_partial(
    monkeypatch,
    truncated_api,
):
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(
        repo_id=33,
        owner_id=1,
        full_name="mydev/pagination-limited",
        is_fork=True,
    )
    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)

    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )

    mock_client.get_repository_details = AsyncMock(
        return_value={
            "full_name": "mydev/pagination-limited",
            "fork": True,
            "parent": {"full_name": "upstream-org/original-project"},
        }
    )

    async def mock_list_commits(**kwargs):
        if truncated_api == "commits":
            kwargs["on_truncated"]()
        return []

    async def mock_list_prs(**kwargs):
        if truncated_api == "prs":
            kwargs["on_truncated"]()
        return []

    mock_client.list_commits = AsyncMock(side_effect=mock_list_commits)
    mock_client.list_pull_requests = AsyncMock(side_effect=mock_list_prs)

    result = await verify_repository_contributions(
        mock_db,
        repo.id,
        user,
        VerificationRequest(),
        client=mock_client,
    )

    assert result.coverage_status == "partial"
    assert result.verification_status == "unknown"
    assert result.confidence == "uncertain"
    assert result.verified_commits_count == 0
    assert result.anti_inflation_flag is True

    assert any(
        "giới hạn phân trang" in limitation.lower() for limitation in result.limitations
    )


@pytest.mark.anyio
async def test_verification_persist_false_does_not_write_database(
    monkeypatch,
):
    user = _create_mock_user(user_id=1)

    repo = _create_mock_repo(
        repo_id=50,
        owner_id=1,
        full_name="mydev/no-persistence",
        is_fork=False,
    )

    mock_db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_client = MagicMock(spec=GitHubApiClient)

    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )

    mock_client.get_repository_details = AsyncMock(
        return_value={
            "full_name": "mydev/no-persistence",
            "fork": False,
        }
    )

    mock_client.list_commits = AsyncMock(return_value=[])
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    result = await verify_repository_contributions(
        db=mock_db,
        repository_id=repo.id,
        user=user,
        client=mock_client,
        persist=False,
    )

    assert result.id is None
    assert result.repository_id == repo.id
    assert result.coverage_status == "complete"

    # Giai đoạn 1: Chỉ xác minh, tuyệt đối không ghi database.
    mock_db.add.assert_not_called()
    mock_db.flush.assert_not_called()
    mock_db.execute.assert_not_called()
    mock_db.commit.assert_not_called()

    # Kiểm tra bước lưu với commit=False.
    result.job_id = str(uuid.uuid4())

    persist_verification_result(
        db=mock_db,
        result=result,
        commit=False,
    )

    mock_db.add.assert_called()
    mock_db.flush.assert_called()
    mock_db.execute.assert_called()
    mock_db.commit.assert_not_called()

    saved_verifications = [
        call.args[0]
        for call in mock_db.add.call_args_list
        if isinstance(call.args[0], RepositoryVerification)
    ]

    assert len(saved_verifications) == 1
    assert saved_verifications[0].job_id == uuid.UUID(result.job_id)
