"""Tests for PBI-011 & PBI-012 Dependency Integration: Background Analysis Jobs &
Pipeline Execution.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.modules.assessments.models
import app.modules.cvs.models
import app.modules.roadmaps.models  # noqa: F401
from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.main import create_app
from app.modules.analysis.inspector import InMemoryContentSource
from app.modules.analysis.models import AnalysisJob
from app.modules.analysis.service import (
    _ANALYSIS_CACHE,
    cancel,
    create,
    retry,
)
from app.modules.github.models import Repository
from app.modules.users.models import User
from app.workers.tasks.analysis import run_analysis


def _mock_user(user_id: int = 1) -> User:
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = "test@example.com"
    return u


def _mock_repo(
    repo_id: int = 10,
    name: str = "demo-repo",
    private: bool = False,
    owner_id: int = 1,
) -> Repository:
    r = MagicMock(spec=Repository)
    r.id = repo_id
    r.name = name
    r.full_name = f"user/{name}"
    r.private = private
    r.owner_id = owner_id
    r.default_branch = "main"
    r.languages = {"Python": 50000}
    return r


def _mock_job(
    job_id: uuid.UUID | None = None,
    user_id: int = 1,
    repo_id: int = 10,
    scope: str = "full",
    status: str = "queued",
    progress: int = 0,
    step: str = "queued",
) -> AnalysisJob:
    j = MagicMock(spec=AnalysisJob)
    j.id = job_id or uuid.uuid4()
    j.user_id = user_id
    j.repo_id = repo_id
    j.scope = scope
    j.status = status
    j.progress = progress
    j.step = step
    j.error_code = None
    j.retry_of = None
    j.execution_token = None
    j.created_at = None
    j.heartbeat_at = None
    j.finished_at = None
    return j


# -----------------------------------------------------------------------------
# 1. Job Lifecycle Unit Tests (Service Layer)
# -----------------------------------------------------------------------------


def test_create_job_service_success(monkeypatch):
    mock_db = MagicMock()
    # require_access succeeds
    mock_db.scalar.side_effect = [1, None]  # 1st: owned check, 2nd: active_job check

    monkeypatch.setattr(
        "app.modules.analysis.service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    job, created = create(mock_db, user_id=1, repo_id=10, scope="full")
    assert created is True
    assert job.user_id == 1
    assert job.repo_id == 10
    assert job.scope == "full"
    assert mock_db.commit.called


def test_create_job_service_idempotent_when_active_exists(monkeypatch):
    mock_db = MagicMock()
    existing_job = _mock_job(status="running")
    mock_db.scalar.side_effect = [1, existing_job]

    monkeypatch.setattr(
        "app.modules.analysis.service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    job, created = create(mock_db, user_id=1, repo_id=10, scope="full")
    assert created is False
    assert job is existing_job


def test_cancel_job_service_transitions_to_cancel_requested():
    mock_db = MagicMock()
    active = _mock_job(status="running")
    mock_db.scalar.return_value = active

    job = cancel(mock_db, user_id=1, job_id=active.id)
    assert job.status == "cancel_requested"
    assert mock_db.commit.called


def test_cancel_terminal_job_raises_conflict():
    mock_db = MagicMock()
    done_job = _mock_job(status="succeeded")
    mock_db.scalar.return_value = done_job

    with pytest.raises(HTTPException) as exc_info:
        cancel(mock_db, user_id=1, job_id=done_job.id)
    assert exc_info.value.status_code == 409


def test_retry_job_service_success(monkeypatch):
    mock_db = MagicMock()
    failed_job = _mock_job(status="failed", repo_id=10, scope="full")
    mock_db.scalar.side_effect = [
        failed_job,  # 1. owned_job
        1,  # 2. require_access in retry
        1,  # 3. require_access in create
        None,  # 4. active_job check in create
    ]

    monkeypatch.setattr(
        "app.modules.analysis.service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    new_job, created = retry(mock_db, user_id=1, job_id=failed_job.id)
    assert created is True
    assert new_job.retry_of == failed_job.id


def test_retry_active_job_raises_conflict():
    mock_db = MagicMock()
    active_job_mock = _mock_job(status="running")
    mock_db.scalar.return_value = active_job_mock

    with pytest.raises(HTTPException) as exc_info:
        retry(mock_db, user_id=1, job_id=active_job_mock.id)
    assert exc_info.value.status_code == 409


# -----------------------------------------------------------------------------
# 2. Worker Task & Static Analysis Execution Tests
# -----------------------------------------------------------------------------


def test_run_analysis_executes_pipeline_and_succeeds(monkeypatch):
    """Verify analysis executes and updates job progress."""
    job_uuid = uuid.uuid4()
    job_record = _mock_job(
        job_id=job_uuid,
        user_id=2,
        repo_id=15,
        scope="full",
        status="queued",
    )
    repo_record = _mock_repo(repo_id=15, name="my-project", private=False)

    fake_source = InMemoryContentSource(
        {
            "main.py": "from fastapi import FastAPI\napp = FastAPI()",
            "requirements.txt": "fastapi>=0.110.0\nuvicorn>=0.28.0",
        }
    )

    mock_db = MagicMock()

    # Mock session_scope contextmanager
    class FakeSessionScope:
        def __enter__(self):
            return mock_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    monkeypatch.setattr(
        "app.modules.auth.service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    # Dynamic return sequence: call 1 = initial job, call 2 = repo record, calls >= 3 =
    # job checkpoints
    def mock_scalar_fn(stmt=None):
        entity = stmt.column_descriptions[0].get("entity") if stmt is not None else None

        if entity is Repository:
            return repo_record

        if entity is AnalysisJob:
            return job_record

    return None

    mock_db.scalar.side_effect = mock_scalar_fn

    result = run_analysis(
        job_id=str(job_uuid),
        custom_source=fake_source,
        custom_commit_sha="1111222233334444555566667777888899990000",
    )

    assert result is not None
    assert result["repository_id"] == 15
    assert len(result["frameworks"]) >= 1
    assert any(f["name"] == "FastAPI" for f in result["frameworks"])
    assert job_record.status == "succeeded"
    assert job_record.progress == 100
    assert job_record.step == "completed"
    assert mock_scalar_fn.call_count >= 6

    # Verifiable evidence in cache
    cache_key = (
        15,
        "1111222233334444555566667777888899990000",
        "full",
        "",
        "",
        "",
    )
    assert cache_key in _ANALYSIS_CACHE


def test_run_analysis_private_repo_without_consent_fails(monkeypatch):
    """Verify private repository without 'repo' OAuth scope fails closed with
    PermissionError.
    """
    job_uuid = uuid.uuid4()
    job_record = _mock_job(
        job_id=job_uuid,
        user_id=3,
        repo_id=20,
        scope="private",
        status="queued",
    )
    private_repo = _mock_repo(repo_id=20, name="secret-repo", private=True)

    mock_db = MagicMock()

    class FakeSessionScope:
        def __enter__(self):
            return mock_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    # Token only has read:user (missing 'repo')
    monkeypatch.setattr(
        "app.modules.auth.service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    mock_db.scalar.side_effect = [
        job_record,
        private_repo,
        job_record,  # in exception handler
    ]

    with pytest.raises(PermissionError) as exc_info:
        run_analysis(job_id=str(job_uuid))

    assert "Private repository analysis requires 'repo' OAuth scope" in str(
        exc_info.value
    )
    assert job_record.status == "failed"
    assert job_record.error_code == "PermissionError"


def test_run_analysis_cancel_requested_terminates_gracefully(monkeypatch):
    """Verify job cancels cleanly when status is cancel_requested."""
    job_uuid = uuid.uuid4()
    job_record = _mock_job(
        job_id=job_uuid,
        user_id=4,
        repo_id=30,
        status="cancel_requested",
    )

    mock_db = MagicMock()

    class FakeSessionScope:
        def __enter__(self):
            return mock_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    mock_db.scalar.return_value = job_record

    res = run_analysis(job_id=str(job_uuid))
    assert res is None
    assert job_record.status == "cancelled"


# -----------------------------------------------------------------------------
# 3. API Endpoints Integration Tests (Jobs & Static Analysis)
# -----------------------------------------------------------------------------


def test_api_jobs_crud_and_csrf(monkeypatch):
    app = create_app()
    user = _mock_user(user_id=10)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: MagicMock()

    fake_job_uuid = uuid.uuid4()
    fake_job = _mock_job(job_id=fake_job_uuid, user_id=10, repo_id=5, scope="full")

    from app.modules.analysis import router as analysis_router_mod

    monkeypatch.setattr(
        analysis_router_mod.service,
        "create",
        MagicMock(return_value=(fake_job, True)),
    )
    monkeypatch.setattr(
        analysis_router_mod.service,
        "owned_job",
        MagicMock(return_value=fake_job),
    )
    monkeypatch.setattr(
        analysis_router_mod.service,
        "cancel",
        MagicMock(return_value=fake_job),
    )
    monkeypatch.setattr(
        analysis_router_mod.service,
        "retry",
        MagicMock(return_value=(fake_job, True)),
    )
    monkeypatch.setattr(
        analysis_router_mod,
        "dispatch",
        MagicMock(),
    )

    with TestClient(app) as client:
        # 1. CSRF validation fails without Origin header
        res_csrf = client.post(
            "/api/v1/analysis/jobs",
            json={"repo_id": 5, "scope": "full"},
        )
        assert res_csrf.status_code == 403

        # 2. Create Job with valid Origin
        res = client.post(
            "/api/v1/analysis/jobs",
            headers={"Origin": "http://localhost:5173"},
            json={"repo_id": 5, "scope": "full"},
        )
        assert res.status_code == 202
        data = res.json()
        assert data["id"] == str(fake_job_uuid)
        assert data["repo_id"] == 5

        # 3. Get Job Status
        res_get = client.get(f"/api/v1/analysis/jobs/{fake_job_uuid}")
        assert res_get.status_code == 200
        assert res_get.json()["id"] == str(fake_job_uuid)

        # 4. Cancel Job
        res_cancel = client.post(
            f"/api/v1/analysis/jobs/{fake_job_uuid}/cancel",
            headers={"Origin": "http://localhost:5173"},
        )
        assert res_cancel.status_code == 202

        # 5. Retry Job
        res_retry = client.post(
            f"/api/v1/analysis/jobs/{fake_job_uuid}/retry",
            headers={"Origin": "http://localhost:5173"},
        )
        assert res_retry.status_code == 202

    app.dependency_overrides.clear()


def test_run_analysis_cancelled_during_inspection_halts_promptly(monkeypatch):
    """Verify job cancels promptly during multi-file inspection if cancel_requested."""
    job_uuid = uuid.uuid4()
    job_record = _mock_job(
        job_id=job_uuid,
        user_id=5,
        repo_id=12,
        scope="full",
        status="queued",
    )
    repo_record = _mock_repo(repo_id=12, name="cancel-repo", private=False)

    fake_source = InMemoryContentSource(
        {
            "package.json": '{"dependencies": {"express": "^4.18.2"}}',
            "requirements.txt": "fastapi>=0.110.0",
        }
    )

    mock_db = MagicMock()

    class FakeSessionScope:
        def __enter__(self):
            return mock_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    monkeypatch.setattr(
        "app.modules.auth.service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    call_count = 0

    def mock_scalar_cancel(stmt=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return job_record
        if call_count == 2:
            return repo_record
        # Simulate user requesting cancellation mid-run
        if call_count >= 3:
            job_record.status = "cancel_requested"
        return job_record

    mock_db.scalar.side_effect = mock_scalar_cancel

    res = run_analysis(
        job_id=str(job_uuid),
        custom_source=fake_source,
        custom_commit_sha="2222333344445555666677778888999900001111",
    )
    assert res is None
    assert job_record.status == "cancelled"


def test_dispatch_handles_os_error_as_503(monkeypatch):
    """Verify dispatch handles OSError with HTTP 503."""
    from app.modules.analysis.router import dispatch

    mock_job = _mock_job(status="queued")
    mock_db = MagicMock()

    def raise_os_error(*args, **kwargs):
        raise OSError("Socket connection refused")

    monkeypatch.setattr("app.modules.analysis.router.enqueue_task", raise_os_error)
    fail_dispatch_mock = MagicMock()
    monkeypatch.setattr(
        "app.modules.analysis.service.fail_dispatch", fail_dispatch_mock
    )

    with pytest.raises(HTTPException) as exc_info:
        dispatch(mock_job, mock_db)

    assert exc_info.value.status_code == 503
    assert "Analysis queue unavailable" in exc_info.value.detail
    fail_dispatch_mock.assert_called_once_with(mock_db, mock_job.id)
