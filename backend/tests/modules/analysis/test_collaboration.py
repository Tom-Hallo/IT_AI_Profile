"""Comprehensive Test Suite for PBI-014: Pull Request, Review, CI &
Problem-Solving Analysis.

Strict compliance with Epic-03, FR-010, Trello ACs & DoD:
- IA-01: Retrieve PRs, reviews and checks/CI from real/authorized GitHub APIs.
- IA-02: Preserve status and timestamps for merged/closed PRs, reviews & checks.
- IA-03: Associate evidence correctly with repo, PR, commit and check.
- IA-04: Never automatically consider rejected PRs or failed CI as poor skills.
- IA-05: Test rate limiting, pagination, permissions, and review documentation.
- DOD-01..05: Full coverage, no mocks in production, clean isolation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.modules.analysis.collaboration_service import (
    analyze_repository_collaboration,
    get_collaboration_evidence_list,
    get_stored_collaboration,
    persist_collaboration_result,
)
from app.modules.analysis.models import (
    CollaborationAnalysis,
    CollaborationEvidence,
)
from app.modules.analysis.schemas import (
    CollaborationAnalysisRequest,
    CollaborationAnalysisResponse,
    CollaborationEvidenceItem,
)
from app.modules.auth.models import OAuthAccount
from app.modules.github.client import (
    GitHubApiClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository, user_repository
from app.modules.users.models import User

# ============================================================================
# Helpers & Fixtures
# ============================================================================


def _create_mock_user(
    user_id: int = 1,
    email: str = "dev@example.com",
    full_name: str = "Nguyen Van Dev",
) -> User:
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = email
    u.full_name = full_name
    return u


def _create_mock_repo(
    repo_id: int = 10,
    name: str = "collaboration-project",
    full_name: str = "mydev/collaboration-project",
    private: bool = False,
    owner_id: int = 1,
    default_branch: str = "main",
) -> Repository:
    r = MagicMock(spec=Repository)
    r.id = repo_id
    r.github_repo_id = 8888 + repo_id
    r.name = name
    r.full_name = full_name
    r.private = private
    r.owner_id = owner_id
    r.default_branch = default_branch
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
    existing_collab: CollaborationAnalysis | None = None,
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
        if "collaboration_analyses" in s_str:
            return existing_collab
        return None

    mock_db.scalar.side_effect = _scalar
    return mock_db


@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def do_connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS ita")
        cursor.close()

    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        yield session

    Base.metadata.drop_all(bind=engine)


# ============================================================================
# Positive Path: Full Collection & Verification (PR, Review, CI, Sequences)
# ============================================================================


@pytest.mark.anyio
async def test_01_full_collaboration_analysis_positive_path(monkeypatch):
    """Xác nhận thu thập đầy đủ PRs, reviews, CI checks và nhận diện chu kỳ."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=10, private=False)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("valid-gh-token", "read:user"),
    )
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _u: repo,
    )

    fake_prs = [
        {
            "number": 1,
            "title": "Feature: Implement authentication",
            "state": "closed",
            "merged_at": "2026-11-01T15:00:00Z",
            "created_at": "2026-11-01T10:00:00Z",
            "updated_at": "2026-11-01T15:00:00Z",
            "html_url": "https://github.com/mydev/collaboration-project/pull/1",
            "user": {"id": 12345, "login": "mydev", "type": "User"},
            "head": {"sha": "sha_pr1_head", "ref": "feat/auth"},
            "base": {"ref": "main"},
        },
        {
            "number": 2,
            "title": "Refactor: Prototype cache strategy",
            "state": "closed",
            "merged_at": None,
            "closed_at": "2026-11-02T12:00:00Z",
            "created_at": "2026-11-02T09:00:00Z",
            "updated_at": "2026-11-02T12:00:00Z",
            "html_url": "https://github.com/mydev/collaboration-project/pull/2",
            "user": {"id": 12345, "login": "mydev", "type": "User"},
            "head": {"sha": "sha_pr2_head", "ref": "experiment/cache"},
            "base": {"ref": "main"},
        },
        {
            "number": 3,
            "title": "Docs: Update contribution guide",
            "state": "open",
            "merged_at": None,
            "created_at": "2026-11-03T08:00:00Z",
            "updated_at": "2026-11-03T08:30:00Z",
            "html_url": "https://github.com/mydev/collaboration-project/pull/3",
            "user": {"id": 99999, "login": "collaborator_bob", "type": "User"},
            "head": {"sha": "sha_pr3_head", "ref": "patch-1"},
            "base": {"ref": "main"},
        },
    ]

    fake_reviews_pr1 = [
        {
            "id": 101,
            "user": {"id": 8888, "login": "reviewer_alice"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-11-01T11:00:00Z",
            "body": "Please add unit tests for token expiration",
            "html_url": "https://github.com/mydev/collaboration-project/pull/1#review-101",
        },
        {
            "id": 102,
            "user": {"id": 8888, "login": "reviewer_alice"},
            "state": "APPROVED",
            "submitted_at": "2026-11-01T14:30:00Z",
            "body": "Looks great now! Approved.",
            "html_url": "https://github.com/mydev/collaboration-project/pull/1#review-102",
        },
    ]

    fake_reviews_pr3 = [
        {
            "id": 103,
            "user": {"id": 12345, "login": "mydev"},
            "state": "APPROVED",
            "submitted_at": "2026-11-03T08:20:00Z",
            "body": "Thank you Bob, approved!",
            "html_url": "https://github.com/mydev/collaboration-project/pull/3#review-103",
        }
    ]

    fake_checks_pr1 = [
        {
            "id": 501,
            "name": "CI / Test & Lint",
            "status": "completed",
            "conclusion": "failure",
            "started_at": "2026-11-01T10:05:00Z",
            "completed_at": "2026-11-01T10:10:00Z",
            "html_url": "https://github.com/mydev/collaboration-project/runs/501",
        },
        {
            "id": 502,
            "name": "CI / Test & Lint",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-11-01T14:00:00Z",
            "completed_at": "2026-11-01T14:08:00Z",
            "html_url": "https://github.com/mydev/collaboration-project/runs/502",
        },
    ]

    fake_statuses_pr1 = [
        {
            "id": 601,
            "context": "security/snyk",
            "state": "success",
            "created_at": "2026-11-01T14:10:00Z",
            "target_url": "https://snyk.io/test/601",
        }
    ]

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.list_pull_requests = AsyncMock(return_value=fake_prs)

    async def _mock_reviews(*args, **kwargs):
        pr_number = kwargs.get("pull_number") or (args[2] if len(args) > 2 else None)
        if pr_number == 1:
            return fake_reviews_pr1
        if pr_number == 3:
            return fake_reviews_pr3
        return []

    mock_client.list_pull_request_reviews = AsyncMock(side_effect=_mock_reviews)

    async def _mock_checks(*args, **kwargs):
        ref = kwargs.get("ref") or (args[2] if len(args) > 2 else None)
        if ref == "sha_pr1_head":
            return fake_checks_pr1
        return []

    mock_client.list_check_runs_for_ref = AsyncMock(side_effect=_mock_checks)

    async def _mock_statuses(*args, **kwargs):
        ref = kwargs.get("ref") or (args[2] if len(args) > 2 else None)
        if ref == "sha_pr1_head":
            return fake_statuses_pr1
        return []

    mock_client.list_commit_statuses_for_ref = AsyncMock(side_effect=_mock_statuses)

    req = CollaborationAnalysisRequest(force_refresh=True)
    res = await analyze_repository_collaboration(
        db=db,
        repository_id=10,
        user=user,
        request=req,
        persist=False,
        custom_client=mock_client,
    )

    # 1. PR counts verification
    assert res.total_prs_analyzed == 3
    assert res.merged_prs_count == 1
    assert res.closed_unmerged_prs_count == 1
    assert res.open_prs_count == 1
    assert res.user_prs_count == 2
    assert res.external_prs_count == 1

    # 2. Review counts verification
    assert res.total_reviews_analyzed == 3
    assert res.approved_reviews_count == 2
    assert res.changes_requested_count == 1
    assert res.user_reviews_conducted_count == 1  # PR3 review authored by mydev
    assert res.user_reviews_received_count == 2  # PR1 reviews received on mydev's PR

    # 3. Check counts verification
    assert res.total_checks_analyzed == 3
    assert res.successful_checks_count == 2
    assert res.failed_checks_count == 1

    # 4. Problem-Solving sequences
    assert res.problem_solving_sequences_count >= 1
    seq_types = [s.trigger_event.get("type") for s in res.problem_solving_sequences]
    assert "review_changes_requested" in seq_types
    assert "ci_check_failure" in seq_types

    # 5. Non-penalization validation
    for obs in res.collaboration_observations:
        desc = obs.description.lower()
        if "kém" in desc:
            assert (
                "không thể hiện" in desc
                or "không phản ánh" in desc
                or "không bị coi là" in desc
                or "tuyệt đối không" in desc
                or "không bị tính điểm trừ" in desc
            )

    # Evidence items
    pr_evs = [e for e in res.evidence if e.evidence_type == "pull_request"]
    assert len(pr_evs) == 3
    closed_ev = [e for e in pr_evs if e.state == "closed_unmerged"][0]
    assert "không phản ánh năng lực kém" in closed_ev.rationale


# ============================================================================
# Negative Competency Non-Penalization Tests (IA-04, Section 8)
# ============================================================================


@pytest.mark.anyio
async def test_02_never_penalize_closed_unmerged_prs_or_failed_ci(monkeypatch):
    """Xác minh hệ thống không suy diễn tiêu cực từ PR bị đóng hoặc CI thất bại."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=11)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("valid-token", "read:user"),
    )
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _u: repo,
    )

    # 100% closed unmerged PRs and 100% failed CI checks
    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.list_pull_requests = AsyncMock(
        return_value=[
            {
                "number": 99,
                "title": "Abandoned trial branch",
                "state": "closed",
                "merged_at": None,
                "created_at": "2026-11-01T10:00:00Z",
                "updated_at": "2026-11-01T12:00:00Z",
                "html_url": "https://github.com/mydev/repo/pull/99",
                "user": {"id": 12345, "login": "mydev"},
                "head": {"sha": "sha_fail"},
            }
        ]
    )
    mock_client.list_pull_request_reviews = AsyncMock(return_value=[])
    mock_client.list_check_runs_for_ref = AsyncMock(
        return_value=[
            {
                "id": 999,
                "name": "Integration Tests",
                "status": "completed",
                "conclusion": "failure",
                "completed_at": "2026-11-01T10:30:00Z",
                "html_url": "https://github.com/mydev/repo/runs/999",
            }
        ]
    )
    mock_client.list_commit_statuses_for_ref = AsyncMock(return_value=[])

    res = await analyze_repository_collaboration(
        db=db,
        repository_id=11,
        user=user,
        request=CollaborationAnalysisRequest(force_refresh=True),
        persist=False,
        custom_client=mock_client,
    )

    assert res.total_prs_analyzed == 1
    assert res.closed_unmerged_prs_count == 1
    assert res.failed_checks_count == 1
    assert res.confidence in ("high", "medium")

    # Verify descriptions emphasize fail-fast and no negative inference
    ci_ev = [e for e in res.evidence if e.evidence_type == "check_run"][0]
    assert "fail-fast" in ci_ev.rationale.lower()
    assert "không phản ánh năng lực kém" in ci_ev.rationale.lower()

    pr_ev = [e for e in res.evidence if e.evidence_type == "pull_request"][0]
    assert "không phản ánh năng lực kém" in pr_ev.rationale.lower()


@pytest.mark.anyio
async def test_03_empty_repository_history_does_not_infer_poor_teamwork(monkeypatch):
    """Repository rỗng hoặc chưa có PR không được quy kết là kỹ năng cộng tác kém."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=12)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("valid-token", "read:user"),
    )
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _u: repo,
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    res = await analyze_repository_collaboration(
        db=db,
        repository_id=12,
        user=user,
        request=CollaborationAnalysisRequest(force_refresh=True),
        persist=False,
        custom_client=mock_client,
    )

    assert res.total_prs_analyzed == 0
    assert res.coverage_status == "complete"
    assert len(res.collaboration_observations) >= 1
    obs = res.collaboration_observations[0]
    assert "không được suy diễn" in obs.description.lower()


# ============================================================================
# Edge Cases & Failure Handling (IA-05, Section 9)
# ============================================================================


@pytest.mark.anyio
async def test_04_rate_limit_handling_marks_partial_coverage(monkeypatch):
    """Khi gặp rate limit lúc lấy PRs, kết quả được đánh dấu partial và uncertain."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=13)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("valid-token", "read:user"),
    )
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _u: repo,
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.list_pull_requests = AsyncMock(
        side_effect=GitHubRateLimitError("Rate limit exceeded")
    )

    res = await analyze_repository_collaboration(
        db=db,
        repository_id=13,
        user=user,
        request=CollaborationAnalysisRequest(force_refresh=True),
        persist=False,
        custom_client=mock_client,
    )

    assert res.coverage_status == "partial"
    assert res.confidence == "uncertain"
    assert any("rate-limit" in lim.lower() for lim in res.limitations)


@pytest.mark.anyio
async def test_05_revoked_token_raises_401(monkeypatch):
    """Token bị thu hồi phải ném mã lỗi HTTP 401 Unauthorized."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=14)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("expired-token", "read:user"),
    )
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _u: repo,
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        side_effect=GitHubTokenRevokedError("Token revoked")
    )

    with pytest.raises(HTTPException) as exc_info:
        await analyze_repository_collaboration(
            db=db,
            repository_id=14,
            user=user,
            request=CollaborationAnalysisRequest(force_refresh=True),
            persist=False,
            custom_client=mock_client,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_06_private_repo_without_consent_raises_404(monkeypatch):
    """Repository private khi chưa có quyền truy cập hoặc consent phải báo 404."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=15, private=True)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _u: repo,
    )

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("valid-token", "repo"),
    )

    def deny_private_consent(_repo, _scope, _db, _user_id):
        raise HTTPException(
            status_code=403,
            detail="Private repository consent required.",
        )

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_private_repo_consent",
        deny_private_consent,
    )

    with pytest.raises(HTTPException) as exc_info:
        await analyze_repository_collaboration(
            db=db,
            repository_id=15,
            user=user,
            request=CollaborationAnalysisRequest(force_refresh=True),
            persist=False,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_07_missing_checks_or_reviews_handled_gracefully(monkeypatch):
    """Khi GitHub trả về 404 cho reviews hoặc check runs, hệ thống chạy mượt mà."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=16)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("valid-token", "read:user"),
    )
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _u: repo,
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.list_pull_requests = AsyncMock(
        return_value=[
            {
                "number": 10,
                "title": "PR with disabled actions",
                "state": "open",
                "created_at": "2026-11-01T10:00:00Z",
                "user": {"id": 12345, "login": "mydev"},
                "head": {"sha": "sha_no_ci"},
            }
        ]
    )
    mock_client.list_pull_request_reviews = AsyncMock(
        side_effect=GitHubNotFoundError("No reviews")
    )
    mock_client.list_check_runs_for_ref = AsyncMock(
        side_effect=GitHubNotFoundError("Checks disabled")
    )
    mock_client.list_commit_statuses_for_ref = AsyncMock(return_value=[])

    res = await analyze_repository_collaboration(
        db=db,
        repository_id=16,
        user=user,
        request=CollaborationAnalysisRequest(force_refresh=True),
        persist=False,
        custom_client=mock_client,
    )

    assert res.total_prs_analyzed == 1
    assert res.total_reviews_analyzed == 0
    assert res.total_checks_analyzed == 0

    assert res.coverage_status == "partial"
    assert res.confidence == "uncertain"

    assert any("reviews" in limitation.lower() for limitation in res.limitations)

    assert any("check runs" in limitation.lower() for limitation in res.limitations)


# ============================================================================
# Persistence, Idempotency & Data Isolation Tests (IA-02, IA-03, DOD-03)
# ============================================================================


def test_08_persist_and_retrieve_collaboration_result(in_memory_db):
    """Kiểm tra lưu trữ nguyên tử và truy xuất dữ liệu phân tích cộng tác từ DB."""
    user = User(
        id=101,
        email="test_collab@example.com",
        full_name="Collab Tester",
        hashed_password="hash",
    )
    repo = Repository(
        id=201,
        external_id="gh-9901",
        name="test-collab-repo",
        full_name="collab/test-collab-repo",
        owner_id=user.id,
        html_url="https://github.com/collab/test-collab-repo",
        private=False,
    )
    in_memory_db.add_all([user, repo])
    in_memory_db.commit()
    in_memory_db.execute(
        user_repository.insert().values(user_id=user.id, repository_id=repo.id)
    )
    in_memory_db.commit()

    collab_resp = CollaborationAnalysisResponse(
        repository_id=repo.id,
        repository_name=repo.name,
        repository_full_name=repo.full_name,
        user_id=user.id,
        total_prs_analyzed=2,
        merged_prs_count=1,
        closed_unmerged_prs_count=1,
        open_prs_count=0,
        user_prs_count=2,
        external_prs_count=0,
        total_reviews_analyzed=1,
        approved_reviews_count=1,
        changes_requested_count=0,
        commented_reviews_count=0,
        dismissed_reviews_count=0,
        user_reviews_conducted_count=0,
        user_reviews_received_count=1,
        total_checks_analyzed=1,
        successful_checks_count=1,
        failed_checks_count=0,
        pending_checks_count=0,
        other_checks_count=0,
        problem_solving_sequences_count=1,
        coverage_status="complete",
        confidence="high",
        time_range=None,
        limitations=[],
        collaboration_observations=[],
        problem_solving_sequences=[],
        summary_data={"key": "val"},
        analyzed_at="2026-11-01T12:00:00+00:00",
        evidence=[
            CollaborationEvidenceItem(
                evidence_type="pull_request",
                target_identifier="PR #1",
                pr_number=1,
                state="merged",
                actor_login="collab_user",
                is_profile_owner=True,
                rationale="Merged PR",
            )
        ],
    )

    # 1. First persistence
    row = persist_collaboration_result(in_memory_db, collab_resp, commit=True)
    assert row.id is not None
    assert row.total_prs_analyzed == 2

    # 2. Retrieval via get_stored_collaboration
    retrieved = get_stored_collaboration(in_memory_db, repo.id, user)
    assert retrieved is not None
    assert retrieved.total_prs_analyzed == 2
    assert len(retrieved.evidence) == 1
    assert retrieved.evidence[0].target_identifier == "PR #1"

    # 3. Reanalysis creates a new snapshot without deleting old evidence
    first_analysis_id = row.id

    collab_resp.analyzed_at = "2026-11-02T12:00:00+00:00"
    collab_resp.time_range = {
        "start": "2026-10-01T00:00:00+00:00",
        "end": "2026-11-01T00:00:00+00:00",
        "timezone": "UTC",
        "label": "custom",
    }
    collab_resp.total_prs_analyzed = 3
    collab_resp.evidence = [
        CollaborationEvidenceItem(
            evidence_type="pull_request",
            target_identifier="PR #2",
            pr_number=2,
            state="open",
            actor_login="collab_user",
            is_profile_owner=True,
            rationale="Updated evidence",
        )
    ]

    row2 = persist_collaboration_result(in_memory_db, collab_resp, commit=True)

    # Each analysis is stored independently
    assert row2.id != first_analysis_id

    # The latest analysis is returned
    retrieved2 = get_stored_collaboration(in_memory_db, repo.id, user)
    assert retrieved2 is not None
    assert retrieved2.id == row2.id
    assert retrieved2.total_prs_analyzed == 3
    assert len(retrieved2.evidence) == 1
    assert retrieved2.evidence[0].target_identifier == "PR #2"

    # The previous snapshot and its evidence remain intact
    old_evidence = in_memory_db.scalars(
        select(CollaborationEvidence).where(
            CollaborationEvidence.analysis_id == first_analysis_id
        )
    ).all()

    assert len(old_evidence) == 1
    assert old_evidence[0].target_identifier == "PR #1"

    all_analyses = in_memory_db.scalars(
        select(CollaborationAnalysis).where(
            CollaborationAnalysis.repository_id == repo.id,
            CollaborationAnalysis.user_id == user.id,
        )
    ).all()

    assert len(all_analyses) == 2
    # Evidence endpoint must only return the latest analysis snapshot
    latest_evidence = get_collaboration_evidence_list(
        in_memory_db,
        repo.id,
        user,
    )

    assert latest_evidence.total == 1
    assert len(latest_evidence.items) == 1
    assert latest_evidence.items[0].target_identifier == "PR #2"
    assert latest_evidence.items[0].target_identifier != "PR #1"

    # Latest overall snapshot may have a custom time range.
    latest = get_stored_collaboration(in_memory_db, repo.id, user)
    assert latest is not None
    assert latest.id == row2.id

    # Default unfiltered cache must not return that custom snapshot.
    unfiltered = get_stored_collaboration(
        in_memory_db,
        repo.id,
        user,
        only_unfiltered=True,
    )
    assert unfiltered is not None
    assert unfiltered.id == first_analysis_id
    assert unfiltered.time_range is None


def test_09_evidence_filtering_and_pagination(in_memory_db):
    """Kiểm tra lọc và phân trang bằng chứng cộng tác theo loại và trạng thái."""
    user = User(
        id=102,
        email="filter@example.com",
        full_name="Filter Tester",
        hashed_password="hash",
    )
    repo = Repository(
        id=202,
        external_id="gh-9902",
        name="test-filter-repo",
        full_name="filter/test-filter-repo",
        owner_id=user.id,
        html_url="https://github.com/filter/test-filter-repo",
        private=False,
    )
    in_memory_db.add_all([user, repo])
    in_memory_db.commit()
    in_memory_db.execute(
        user_repository.insert().values(user_id=user.id, repository_id=repo.id)
    )
    in_memory_db.commit()

    collab = CollaborationAnalysis(
        repository_id=repo.id,
        user_id=user.id,
        total_prs_analyzed=3,
        coverage_status="complete",
        confidence="high",
        limitations=[],
        collaboration_observations=[],
        problem_solving_observations=[],
        summary_data={},
    )
    in_memory_db.add(collab)
    in_memory_db.flush()

    # Add evidence rows
    ev1 = CollaborationEvidence(
        analysis_id=collab.id,
        repository_id=repo.id,
        user_id=user.id,
        evidence_type="pull_request",
        target_identifier="PR #1",
        pr_number=1,
        state="merged",
        rationale="Merged",
    )
    ev2 = CollaborationEvidence(
        analysis_id=collab.id,
        repository_id=repo.id,
        user_id=user.id,
        evidence_type="review",
        target_identifier="Review #101",
        pr_number=1,
        state="APPROVED",
        rationale="Approved",
    )
    ev3 = CollaborationEvidence(
        analysis_id=collab.id,
        repository_id=repo.id,
        user_id=user.id,
        evidence_type="check_run",
        target_identifier="CheckRun #201",
        pr_number=1,
        state="completed",
        conclusion="failure",
        rationale="CI fail-fast",
    )
    in_memory_db.add_all([ev1, ev2, ev3])
    in_memory_db.commit()

    # Filter by evidence_type = 'review'
    reviews = get_collaboration_evidence_list(
        in_memory_db, repo.id, user, evidence_type="review"
    )
    assert reviews.total == 1
    assert reviews.items[0].target_identifier == "Review #101"

    # Filter by state = 'merged'
    merged = get_collaboration_evidence_list(
        in_memory_db, repo.id, user, state="merged"
    )
    assert merged.total == 1
    assert merged.items[0].target_identifier == "PR #1"

    failed_checks = get_collaboration_evidence_list(
        in_memory_db, repo.id, user, evidence_type="check_run", state="failure"
    )
    assert failed_checks.total == 1

    newer = CollaborationAnalysis(
        repository_id=repo.id,
        user_id=user.id,
        coverage_status="complete",
        confidence="high",
        limitations=[],
        collaboration_observations=[],
        problem_solving_observations=[],
        summary_data={},
    )
    in_memory_db.add(newer)
    in_memory_db.commit()
    pinned = get_collaboration_evidence_list(
        in_memory_db, repo.id, user, analysis_id=collab.id, state="failure"
    )
    assert pinned.total == 1

    # Filter by pr_number = 1
    by_pr = get_collaboration_evidence_list(
        in_memory_db, repo.id, user, pr_number=1, analysis_id=collab.id
    )
    assert by_pr.total == 3


# ============================================================================
# API Router Integration Tests (IA-01..05, DOD-02..04)
# ============================================================================


def test_10_api_endpoints_trigger_and_get(in_memory_db, monkeypatch):
    """Kiểm tra gọi API POST / GET / GET evidence qua TestClient."""
    user = User(
        id=103,
        email="api_user@example.com",
        full_name="API User",
        hashed_password="hash",
    )
    repo = Repository(
        id=203,
        external_id="gh-9903",
        name="api-collab-repo",
        full_name="api/api-collab-repo",
        owner_id=user.id,
        html_url="https://github.com/api/api-collab-repo",
        private=False,
    )
    in_memory_db.add_all([user, repo])
    in_memory_db.commit()
    in_memory_db.execute(
        user_repository.insert().values(user_id=user.id, repository_id=repo.id)
    )
    in_memory_db.commit()

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: in_memory_db

    fake_resp = CollaborationAnalysisResponse(
        repository_id=repo.id,
        repository_name=repo.name,
        repository_full_name=repo.full_name,
        user_id=user.id,
        total_prs_analyzed=1,
        merged_prs_count=1,
        closed_unmerged_prs_count=0,
        open_prs_count=0,
        user_prs_count=1,
        external_prs_count=0,
        total_reviews_analyzed=0,
        approved_reviews_count=0,
        changes_requested_count=0,
        commented_reviews_count=0,
        dismissed_reviews_count=0,
        user_reviews_conducted_count=0,
        user_reviews_received_count=0,
        total_checks_analyzed=0,
        successful_checks_count=0,
        failed_checks_count=0,
        pending_checks_count=0,
        other_checks_count=0,
        problem_solving_sequences_count=0,
        coverage_status="complete",
        confidence="high",
        time_range=None,
        limitations=[],
        collaboration_observations=[],
        problem_solving_sequences=[],
        summary_data={},
        analyzed_at="2026-11-01T12:00:00+00:00",
        evidence=[],
    )

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_router.analyze_repository_collaboration",
        AsyncMock(return_value=fake_resp),
    )

    client = TestClient(app)

    # 1. Trigger POST
    post_res = client.post(f"/api/v1/repositories/{repo.id}/collaboration", json={})
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["total_prs_analyzed"] == 1
    assert data["merged_prs_count"] == 1

    # 2. Get latest before persisting returns 404
    get_404 = client.get(f"/api/v1/repositories/{repo.id}/collaboration")
    assert get_404.status_code == 404

    # 3. Persist and Get latest returns 200
    persist_collaboration_result(in_memory_db, fake_resp, commit=True)
    get_200 = client.get(f"/api/v1/repositories/{repo.id}/collaboration")
    assert get_200.status_code == 200
    assert get_200.json()["total_prs_analyzed"] == 1

    # 4. Evidence list GET returns 200
    ev_res = client.get(f"/api/v1/repositories/{repo.id}/collaboration/evidence")
    assert ev_res.status_code == 200
    assert "items" in ev_res.json()


def test_11_cross_user_isolation(in_memory_db):
    """Kiểm tra không bị rò rỉ dữ liệu giữa hai người dùng (cross-user isolation)."""
    user_a = User(
        id=104, email="user_a@example.com", full_name="User A", hashed_password="h"
    )
    user_b = User(
        id=105, email="user_b@example.com", full_name="User B", hashed_password="h"
    )
    repo_a = Repository(
        id=204,
        external_id="gh-9904",
        name="repo-a",
        full_name="a/repo-a",
        owner_id=user_a.id,
        html_url="https://github.com/a/repo-a",
        private=True,
    )

    in_memory_db.add_all([user_a, user_b, repo_a])
    in_memory_db.commit()
    in_memory_db.execute(
        user_repository.insert().values(user_id=user_a.id, repository_id=repo_a.id)
    )
    in_memory_db.commit()

    app = create_app()
    # User B tries to access User A's private repository
    app.dependency_overrides[get_current_user] = lambda: user_b
    app.dependency_overrides[get_session] = lambda: in_memory_db

    client = TestClient(app)
    res = client.get(f"/api/v1/repositories/{repo_a.id}/collaboration")
    assert res.status_code == 404


@pytest.mark.parametrize(
    "read_function",
    [get_stored_collaboration, get_collaboration_evidence_list],
)
@pytest.mark.parametrize(
    ("granted", "revoked"),
    [
        (False, False),
        (False, True),
        (True, True),
    ],
)
def test_12_private_consent_revocation_blocks_stored_collaboration(
    monkeypatch, read_function, granted, revoked
):
    """Private evidence không được đọc khi consent thiếu hoặc đã bị thu hồi."""
    from datetime import UTC, datetime

    from app.modules.consent.service import POLICY_VERSION

    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=120, private=True)

    consent = MagicMock()
    consent.granted = granted
    consent.revoked_at = datetime.now(UTC) if revoked else None
    consent.policy_version = POLICY_VERSION

    db = MagicMock()

    def fake_scalar(statement):
        sql = str(statement).lower()

        if "private_consents" in sql:
            return consent
        if "repositories" in sql:
            return repo

        return None

    db.scalar.side_effect = fake_scalar

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _repo_id, _user: repo,
    )

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("test-token", "repo"),
    )

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.has_private_access",
        lambda _db, _uid: True,
    )

    with pytest.raises(HTTPException) as exc_info:
        read_function(db, repo.id, user)

    assert exc_info.value.status_code == 403


@pytest.mark.parametrize(
    "read_function",
    [get_stored_collaboration, get_collaboration_evidence_list],
)
def test_13_valid_private_consent_allows_collaboration_read(monkeypatch, read_function):
    """Consent hợp lệ không được chặn nhầm việc đọc dữ liệu private."""
    from app.modules.consent.service import POLICY_VERSION

    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=121, private=True)

    consent = MagicMock()
    consent.granted = True
    consent.revoked_at = None
    consent.policy_version = POLICY_VERSION

    db = MagicMock()

    def fake_scalar(statement):
        sql = str(statement).lower()

        if "private_consents" in sql:
            return consent
        if "repositories" in sql:
            return repo

        return None

    db.scalar.side_effect = fake_scalar
    db.scalars.return_value.all.return_value = []

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _repo_id, _user: repo,
    )

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("test-token", "repo"),
    )

    monkeypatch.setattr(
        "app.modules.analysis.verification_service.has_private_access",
        lambda _db, _uid: True,
    )

    result = read_function(db, repo.id, user)

    if read_function is get_stored_collaboration:
        assert result is None
    else:
        assert result.repository_id == repo.id
        assert result.total == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "truncated_source",
    ["reviews", "checks", "statuses"],
)
async def test_14_pagination_truncation_marks_partial(monkeypatch, truncated_source):
    """Dữ liệu vượt giới hạn phân trang phải được đánh dấu partial."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=140)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("valid-token", "read:user"),
    )

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _user: repo,
    )

    mock_client = MagicMock(spec=GitHubApiClient)

    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )

    mock_client.list_pull_requests = AsyncMock(
        return_value=[
            {
                "number": 1,
                "title": "Test pagination",
                "state": "open",
                "created_at": "2026-11-01T10:00:00Z",
                "user": {"id": 12345, "login": "mydev"},
                "head": {"sha": "abc123"},
            }
        ]
    )

    async def fake_collection(*args, **kwargs):
        callback = kwargs.get("on_truncated")

        if truncated_source == kwargs.get("source_for_test"):
            raise AssertionError("Unexpected test argument")

        if callback is not None:
            callback()

        return []

    async def collect_reviews(*args, **kwargs):
        if truncated_source == "reviews":
            return await fake_collection(*args, **kwargs)
        return []

    async def collect_checks(*args, **kwargs):
        if truncated_source == "checks":
            return await fake_collection(*args, **kwargs)
        return []

    async def collect_statuses(*args, **kwargs):
        if truncated_source == "statuses":
            return await fake_collection(*args, **kwargs)
        return []

    mock_client.list_pull_request_reviews = AsyncMock(side_effect=collect_reviews)
    mock_client.list_check_runs_for_ref = AsyncMock(side_effect=collect_checks)
    mock_client.list_commit_statuses_for_ref = AsyncMock(side_effect=collect_statuses)

    result = await analyze_repository_collaboration(
        db=db,
        repository_id=repo.id,
        user=user,
        request=CollaborationAnalysisRequest(force_refresh=True),
        persist=False,
        custom_client=mock_client,
    )

    assert result.total_prs_analyzed == 1
    assert result.coverage_status == "partial"
    assert result.confidence == "uncertain"
    assert any("phân trang" in limitation.lower() for limitation in result.limitations)


@pytest.mark.anyio
async def test_15_invalid_time_range_returns_422(monkeypatch):
    """Khoảng thời gian không hợp lệ không được bị bỏ qua."""
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=150)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("valid-token", "read:user"),
    )
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _user: repo,
    )

    mock_client = MagicMock(spec=GitHubApiClient)
    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )
    mock_client.list_pull_requests = AsyncMock(return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        await analyze_repository_collaboration(
            db=db,
            repository_id=repo.id,
            user=user,
            request=CollaborationAnalysisRequest(
                mode="custom",
                start_date="2026-11-10",
                end_date="2026-11-01",
                force_refresh=True,
            ),
            persist=False,
            custom_client=mock_client,
        )

    assert exc_info.value.status_code == 422
    mock_client.list_pull_requests.assert_not_awaited()


@pytest.mark.anyio
async def test_16_branch_filter_uses_pr_base_branch(monkeypatch):
    user = _create_mock_user(user_id=1)
    repo = _create_mock_repo(repo_id=160)
    db = make_mock_db(repo)

    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda _db, _uid: ("valid-token", "read:user"),
    )
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.verify_repository_access",
        lambda _db, _rid, _user: repo,
    )

    mock_client = MagicMock(spec=GitHubApiClient)

    mock_client.get_authenticated_user = AsyncMock(
        return_value={"id": 12345, "login": "mydev"}
    )

    mock_client.list_pull_requests = AsyncMock(
        return_value=[
            {
                "number": 1,
                "state": "open",
                "created_at": "2026-11-01T10:00:00Z",
                "user": {"id": 12345, "login": "mydev"},
                "head": {"sha": "sha1", "ref": "feature/login"},
                "base": {"ref": "main"},
            },
            {
                "number": 2,
                "state": "open",
                "created_at": "2026-11-02T10:00:00Z",
                "user": {"id": 12345, "login": "mydev"},
                "head": {"sha": "sha2", "ref": "feature/search"},
                "base": {"ref": "develop"},
            },
        ]
    )

    mock_client.list_pull_request_reviews = AsyncMock(return_value=[])
    mock_client.list_check_runs_for_ref = AsyncMock(return_value=[])
    mock_client.list_commit_statuses_for_ref = AsyncMock(return_value=[])

    result = await analyze_repository_collaboration(
        db=db,
        repository_id=repo.id,
        user=user,
        request=CollaborationAnalysisRequest(
            branch="develop",
            force_refresh=True,
        ),
        persist=False,
        custom_client=mock_client,
    )

    assert result.total_prs_analyzed == 1
    assert result.summary_data["branch_filter"] == "develop"
    assert result.summary_data["branch_filter_type"] == "base"

    pr_evidence = [
        item for item in result.evidence if item.evidence_type == "pull_request"
    ]

    assert len(pr_evidence) == 1
    assert pr_evidence[0].pr_number == 2


@pytest.mark.anyio
async def test_collaboration_custom_dates_include_only_in_window_events(monkeypatch):
    repo = _create_mock_repo()
    db = make_mock_db(repo)
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda *_: ("valid-token", "read:user"),
    )
    client = MagicMock(spec=GitHubApiClient)
    client.get_authenticated_user.return_value = {"id": 12345, "login": "mydev"}
    client.list_pull_requests.return_value = [
        {
            "number": 1,
            "state": "closed",
            "created_at": "2026-11-01T10:00:00Z",
            "merged_at": "2026-11-02T00:00:00Z",
            "head": {"sha": "abc"},
        },
    ]
    client.list_pull_request_reviews.return_value = [
        {
            "id": 1,
            "state": "APPROVED",
            "submitted_at": "2026-11-01T11:00:00Z",
            "user": {"id": 12345},
        },
        {"id": 2, "state": "APPROVED", "submitted_at": "2026-11-02T00:00:00Z"},
    ]
    client.list_check_runs_for_ref.return_value = [
        {
            "id": 1,
            "name": "build",
            "conclusion": "success",
            "completed_at": "2026-11-01T11:00:00Z",
        },
        {
            "id": 2,
            "name": "deploy",
            "conclusion": "failure",
            "completed_at": "2026-11-02T00:00:00Z",
        },
    ]
    client.list_commit_statuses_for_ref.return_value = []

    result = await analyze_repository_collaboration(
        db,
        repo.id,
        _create_mock_user(),
        CollaborationAnalysisRequest(
            mode="custom", start_date="2026-11-01", end_date="2026-11-01"
        ),
        persist=False,
        custom_client=client,
    )

    assert result.total_prs_analyzed == result.open_prs_count == 1
    assert result.total_reviews_analyzed == result.user_reviews_conducted_count == 1
    assert result.total_checks_analyzed == result.successful_checks_count == 1


@pytest.mark.anyio
async def test_same_sha_ci_is_fetched_and_counted_once(monkeypatch):
    repo = _create_mock_repo()
    monkeypatch.setattr(
        "app.modules.analysis.collaboration_service.get_user_github_token",
        lambda *_: ("valid-token", "read:user"),
    )
    client = MagicMock(spec=GitHubApiClient)
    client.get_authenticated_user.return_value = {"id": 12345, "login": "mydev"}
    client.list_pull_requests.return_value = [
        {"number": n, "state": "open", "head": {"sha": "same-sha"}} for n in (1, 2)
    ]
    client.list_pull_request_reviews.return_value = []
    client.list_check_runs_for_ref.return_value = [
        {"id": 10, "name": "build", "conclusion": "failure"}
    ]
    client.list_commit_statuses_for_ref.return_value = []

    result = await analyze_repository_collaboration(
        make_mock_db(repo),
        repo.id,
        _create_mock_user(),
        CollaborationAnalysisRequest(),
        persist=False,
        custom_client=client,
    )

    client.list_check_runs_for_ref.assert_awaited_once()
    client.list_commit_statuses_for_ref.assert_awaited_once()
    assert result.total_checks_analyzed == result.failed_checks_count == 1
    assert {e.pr_number for e in result.evidence if e.evidence_type == "check_run"} == {
        1,
        2,
    }
