"""Tests for Service layer and API endpoints (Authorization, Scopes, Time-range,
Reanalysis, Evidence) (PBI-012).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.main import create_app
from app.modules.analysis.evidence import UTC, EvidenceRecord
from app.modules.analysis.inspector import InMemoryContentSource
from app.modules.analysis.schemas import RepositoryAnalysisRequest
from app.modules.analysis.service import (
    analyze_repository,
    get_analysis_evidence,
    verify_private_repo_consent,
    verify_repository_access,
)
from app.modules.github.models import Repository
from app.modules.users.models import User


def _create_mock_user(user_id: int = 1, email: str = "dev@example.com") -> User:
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = email
    return u


def _create_mock_repo(
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


# --------------------------------------------------------------------------
# Authorization & Consent Tests (Requirements 5.8, 5.9, 5.10)
# --------------------------------------------------------------------------


def test_unauthorized_repository_access_raises_404():
    """Requirement 5.10: Unauthorized repository access."""
    mock_db = MagicMock()
    mock_db.scalar.return_value = None  # User không có quyền truy cập repo này
    user = _create_mock_user(user_id=1)

    with pytest.raises(HTTPException) as exc_info:
        verify_repository_access(mock_db, repository_id=999, user=user)
    assert exc_info.value.status_code == 404
    assert (
        "Không tìm thấy repository hoặc bạn không có quyền truy cập"
        in exc_info.value.detail
    )


def test_private_repository_without_consent_raises_403():
    """Requirement 5.9: Private repository without consent / missing 'repo' scope."""
    private_repo = _create_mock_repo(repo_id=20, private=True)

    # 1. Scope rỗng hoặc chỉ có read:user
    with pytest.raises(HTTPException) as exc_info:
        verify_private_repo_consent(private_repo, scope="read:user")
    assert exc_info.value.status_code == 403
    assert "yêu cầu quyền truy cập scope 'repo'" in exc_info.value.detail

    # 2. Scope None
    with pytest.raises(HTTPException) as exc_info:
        verify_private_repo_consent(private_repo, scope=None)
    assert exc_info.value.status_code == 403


def test_private_repository_with_valid_permission():
    """Requirement 5.8: Private repository with valid permission."""
    private_repo = _create_mock_repo(repo_id=20, private=True)
    # Có scope 'repo' hợp lệ -> không ném lỗi
    verify_private_repo_consent(private_repo, scope="read:user,repo")


# --------------------------------------------------------------------------
# Scope & Time-range Propagation Tests (Requirement 5.15)
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_scope_mismatch_raises_400(monkeypatch):
    """Requirement 5.15: Scope propagation and validation."""
    monkeypatch.setattr(
        "app.modules.analysis.service.has_private_access", lambda _db, _uid: True
    )
    mock_db = MagicMock()
    public_repo = _create_mock_repo(repo_id=1, private=False)
    private_repo = _create_mock_repo(repo_id=2, private=True)
    user = _create_mock_user()

    # Yêu cầu scope="private" nhưng repo là public
    mock_db.scalar.return_value = public_repo
    req_private = RepositoryAnalysisRequest(scope="private")
    with pytest.raises(HTTPException) as exc_info:
        await analyze_repository(mock_db, 1, user, req_private)
    assert exc_info.value.status_code == 400
    assert "không phù hợp với phạm vi phân tích 'private'" in exc_info.value.detail

    # Yêu cầu scope="public" nhưng repo là private
    mock_db.scalar.return_value = private_repo
    req_public = RepositoryAnalysisRequest(scope="public")
    with pytest.raises(HTTPException) as exc_info:
        await analyze_repository(mock_db, 2, user, req_public)
    assert exc_info.value.status_code == 400
    assert "không phù hợp với phạm vi phân tích 'public'" in exc_info.value.detail


@pytest.mark.anyio
async def test_time_range_propagation(monkeypatch):
    """Requirement 5.15: Time-range selection propagation (PBI-010 integration)."""
    mock_db = MagicMock()
    repo = _create_mock_repo(repo_id=5, private=False)
    mock_db.scalar.return_value = repo
    user = _create_mock_user()

    monkeypatch.setattr(
        "app.modules.analysis.service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    req = RepositoryAnalysisRequest(
        mode="month",
        month="2026-10",
        timezone="UTC",
    )
    fake_source = InMemoryContentSource({"main.py": "print('hello')"})

    result = await analyze_repository(
        db=mock_db,
        repository_id=5,
        user=user,
        request=req,
        custom_source=fake_source,
    )
    assert result["time_range"] is not None
    assert result["time_range"]["start_utc"] == "2026-10-01T00:00:00+00:00"
    assert result["time_range"]["end_utc"] == "2026-11-01T00:00:00+00:00"


# --------------------------------------------------------------------------
# Reanalysis Preserving Evidence Identity Tests (Requirement 5.14)
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_reanalysis_preserves_evidence_identity(monkeypatch):
    """Requirement 5.14: Reanalysis preserving evidence identity."""
    mock_db = MagicMock()
    repo = _create_mock_repo(repo_id=8, private=False)
    mock_db.scalar.return_value = repo
    user = _create_mock_user()

    monkeypatch.setattr(
        "app.modules.analysis.service.get_user_github_token",
        lambda _db, _uid: ("fake-token", "read:user"),
    )

    commit_a_sha = "1111111111111111111111111111111111111111"
    commit_b_sha = "2222222222222222222222222222222222222222"

    # 1. Phân tích Commit A
    commit_a_files = {
        "package.json": '{"name": "a", "dependencies": {"express": "4.18.0"}}'
    }
    source_a = InMemoryContentSource(commit_a_files)

    # Chạy phân tích A
    req = RepositoryAnalysisRequest()
    await analyze_repository(
        db=mock_db,
        repository_id=8,
        user=user,
        request=req,
        custom_source=source_a,
        custom_commit_sha=commit_a_sha,
    )

    # 2. Phân tích Commit B với phiên bản khác
    commit_b_files = {"requirements.txt": "fastapi>=0.110.0\nuvicorn>=0.28.0"}
    source_b = InMemoryContentSource(commit_b_files)

    res_b = await analyze_repository(
        db=mock_db,
        repository_id=8,
        user=user,
        request=req,
        custom_source=source_b,
        custom_commit_sha=commit_b_sha,
    )
    assert res_b["commit_sha"] == commit_b_sha

    # 3. Lấy lại kết quả phân tích theo commit_sha và xác minh bằng chứng không bị đè
    evidence_a = get_analysis_evidence(mock_db, 8, user, commit_sha=commit_a_sha)
    assert len(evidence_a) > 0
    assert all(e.commit_sha == commit_a_sha for e in evidence_a)
    assert any(e.classification == "Express" for e in evidence_a)

    evidence_b = get_analysis_evidence(mock_db, 8, user, commit_sha=commit_b_sha)
    assert len(evidence_b) > 0
    assert all(e.commit_sha == commit_b_sha for e in evidence_b)
    assert any(e.classification == "FastAPI" for e in evidence_b)


# --------------------------------------------------------------------------
# API Endpoints Integration Tests
# --------------------------------------------------------------------------


def test_api_trigger_and_get_analysis(monkeypatch):
    app = create_app()

    user = _create_mock_user(user_id=7)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: MagicMock()

    fake_analysis_result = {
        "repository_id": 9,
        "commit_sha": "abcd" * 10,
        "analyzed_at": "2026-11-09T12:00:00+00:00",
        "scope": "all",
        "time_range": None,
        "structure": {"total_files": 10, "inspected_files": 5, "ignored_files": 5},
        "languages": [
            {
                "name": "Python",
                "primary": True,
                "bytes_count": 1000,
                "percentage": 100.0,
                "file_count": 5,
                "evidence_count": 2,
            }
        ],
        "frameworks": [
            {
                "name": "FastAPI",
                "category": "web_framework",
                "ecosystem": "Python",
                "version": "0.110.0",
                "status": "confirmed",
                "confidence": "high",
                "evidence_count": 1,
            }
        ],
        "architecture": [
            {
                "pattern": "api_service",
                "name": "API-Oriented Architecture",
                "description": "REST API service",
                "confidence": "high",
                "evidence_count": 1,
            }
        ],
        "evidence": [
            {
                "repository_id": 9,
                "commit_sha": "abcd" * 10,
                "file_path": "main.py",
                "finding_type": "framework",
                "classification": "FastAPI",
                "evidence_source": "source_code",
                "detection_method": "manifest_parsing",
                "confidence": "high",
                "confidence_score": 1.0,
                "rationale": "FastAPI import detected",
                "scope": "all",
                "timestamp": "2026-11-09T12:00:00+00:00",
            }
        ],
        "budget": {
            "inspected_files": 5,
            "inspected_bytes": 1000,
            "skipped_oversized_files": 0,
            "limit_reached": False,
        },
    }

    from app.modules.analysis import router as analysis_router_mod

    monkeypatch.setattr(
        analysis_router_mod,
        "analyze_repository",
        AsyncMock(return_value=fake_analysis_result),
    )
    monkeypatch.setattr(
        analysis_router_mod,
        "get_latest_analysis",
        MagicMock(return_value=fake_analysis_result),
    )
    monkeypatch.setattr(
        analysis_router_mod,
        "get_analysis_evidence",
        MagicMock(
            return_value=[
                EvidenceRecord.model_validate(e)
                for e in fake_analysis_result["evidence"]
            ]
        ),
    )

    with TestClient(app) as client:
        # 1. Trigger Analysis
        res = client.post(
            "/api/v1/repositories/9/analyze",
            json={"scope": "all", "mode": "preset", "preset": "1m"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["repository_id"] == 9
        assert len(data["frameworks"]) == 1
        assert data["frameworks"][0]["name"] == "FastAPI"

        # 2. Get Latest Analysis
        res_get = client.get("/api/v1/repositories/9/analysis")
        assert res_get.status_code == 200
        assert res_get.json()["repository_id"] == 9

        # 3. Get Evidence Records
        res_ev = client.get("/api/v1/repositories/9/analysis/evidence")
        assert res_ev.status_code == 200
        ev_data = res_ev.json()
        assert ev_data["repository_id"] == 9
        assert ev_data["total"] == 1
        assert ev_data["items"][0]["classification"] == "FastAPI"

    app.dependency_overrides.clear()


def test_get_latest_analysis_loads_from_database_on_cache_miss():
    """Verify get_latest_analysis fetches and reconstructs report from DB when not in L1
    cache.
    """
    from datetime import datetime

    from app.modules.analysis.models import AnalysisEvidence, AnalysisReport
    from app.modules.analysis.service import _ANALYSIS_CACHE, get_latest_analysis

    # Ensure repository 99 is not in _ANALYSIS_CACHE
    to_delete = [k for k in _ANALYSIS_CACHE if k[0] == 99]
    for k in to_delete:
        del _ANALYSIS_CACHE[k]

    mock_db = MagicMock()
    # 1st call: verify_repository_access
    # 2nd call: select(AnalysisReport)
    mock_repo = _create_mock_repo(repo_id=99)
    mock_report = MagicMock(spec=AnalysisReport)
    mock_report.id = 1
    mock_report.repository_id = 99
    mock_report.commit_sha = "aabbcc" * 6 + "1234"
    mock_report.analyzed_at = datetime(2026, 11, 9, 12, 0, 0, tzinfo=UTC)
    mock_report.scope = "all"
    mock_report.time_range = None
    mock_report.structure = {
        "total_files": 2,
        "inspected_files": 2,
        "ignored_files": 0,
    }
    mock_report.languages = [
        {
            "name": "Python",
            "primary": True,
            "file_count": 2,
            "evidence_count": 1,
            "bytes_count": 100,
            "percentage": 100.0,
        }
    ]
    mock_report.frameworks = []
    mock_report.architecture = []
    mock_report.budget = {"inspected_files": 2}

    mock_evidence = MagicMock(spec=AnalysisEvidence)
    mock_evidence.repository_id = 99
    mock_evidence.commit_sha = mock_report.commit_sha
    mock_evidence.file_path = "app.py"
    mock_evidence.finding_type = "language"
    mock_evidence.classification = "Python"
    mock_evidence.evidence_source = "source_code"
    mock_evidence.detection_method = "content_inspection"
    mock_evidence.confidence = "high"
    mock_evidence.confidence_score = 1.0
    mock_evidence.rationale = "Python syntax"
    mock_evidence.line_number = 1
    mock_evidence.matched_content = "def test():"
    mock_evidence.scope = "all"
    mock_evidence.time_range = None
    mock_evidence.timestamp = datetime(2026, 11, 9, 12, 0, 0, tzinfo=UTC)

    mock_db.scalar.side_effect = [mock_repo, mock_report]
    mock_db.scalars.return_value.all.return_value = [mock_evidence]

    user = _create_mock_user(user_id=1)
    res = get_latest_analysis(mock_db, 99, user)

    assert res["repository_id"] == 99
    assert res["commit_sha"] == mock_report.commit_sha
    assert len(res["evidence"]) == 1
    assert res["evidence"][0]["classification"] == "Python"
    # Cached for subsequent calls
    assert (99, mock_report.commit_sha) in _ANALYSIS_CACHE


# --------------------------------------------------------------------------
# Regression Tests: Scenario Verification & Validation Rules
# --------------------------------------------------------------------------


def test_regression_scenario_without_and_with_time_range(monkeypatch):
    """Verify analysis request handling with and without PBI-010 time-range
    filtering.
    """
    app = create_app()
    user = _create_mock_user(user_id=1)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: MagicMock()

    from app.modules.analysis import router as analysis_router_mod

    mock_analyze = AsyncMock(
        return_value={
            "repository_id": 1,
            "commit_sha": "1234567890abcdef1234567890abcdef12345678",
            "analyzed_at": "2026-11-10T00:00:00+00:00",
            "scope": "all",
            "time_range": {
                "start_utc": "2026-11-08T17:00:00+00:00",
                "end_utc": "2026-11-10T17:00:00+00:00",
                "timezone": "Asia/Ho_Chi_Minh",
            },
            "structure": {"total_files": 10, "inspected_files": 5, "ignored_files": 5},
            "languages": [],
            "frameworks": [],
            "architecture": [],
            "evidence": [],
            "budget": {
                "inspected_files": 5,
                "inspected_bytes": 500,
                "skipped_oversized_files": 0,
                "limit_reached": False,
            },
        }
    )
    monkeypatch.setattr(analysis_router_mod, "analyze_repository", mock_analyze)

    with TestClient(app) as client:
        # 1. Without time-range filtering
        res_no_timerange = client.post(
            "/api/v1/repositories/1/analyze",
            json={"scope": "all", "branch": "master"},
        )
        assert res_no_timerange.status_code == 200

        # 2. With valid PBI-010 time-range filtering (Current Scenario)
        scenario_payload = {
            "branch": "master",
            "scope": "all",
            "mode": "custom",
            "start_date": "2026-11-09",
            "end_date": "2026-11-10",
            "timezone": "Asia/Ho_Chi_Minh",
        }
        res_with_timerange = client.post(
            "/api/v1/repositories/1/analyze",
            json=scenario_payload,
        )
        assert res_with_timerange.status_code == 200
        call_req = mock_analyze.call_args.kwargs["request"]
        assert call_req.branch == "master"
        assert call_req.scope == "all"
        assert call_req.mode == "custom"
        assert call_req.timezone == "Asia/Ho_Chi_Minh"

        # 3. Normalized scope "All code in repo"
        res_normalized_scope = client.post(
            "/api/v1/repositories/1/analyze",
            json={"scope": "All code in repo", "branch": "master"},
        )
        assert res_normalized_scope.status_code == 200

        # 4. Invalid scope value returns 422
        res_invalid_scope = client.post(
            "/api/v1/repositories/1/analyze",
            json={"scope": "unsupported_scope"},
        )
        assert res_invalid_scope.status_code == 422
        assert "scope" in res_invalid_scope.text

        # 5. Invalid date range (start_date > end_date) returns 422
        monkeypatch.setattr(
            analysis_router_mod,
            "analyze_repository",
            analyze_repository,  # call real service function
        )
        # Mock repository access and token for service call
        mock_db = MagicMock()
        mock_repo = _create_mock_repo(repo_id=1, private=False)
        mock_db.scalar.return_value = mock_repo
        app.dependency_overrides[get_session] = lambda: mock_db
        monkeypatch.setattr(
            "app.modules.analysis.service.get_user_github_token",
            lambda _db, _uid: ("fake_token", "read:user"),
        )

        res_invalid_date = client.post(
            "/api/v1/repositories/1/analyze",
            json={
                "scope": "all",
                "mode": "custom",
                "start_date": "2026-11-10",
                "end_date": "2026-11-09",
                "timezone": "Asia/Ho_Chi_Minh",
            },
        )
        assert res_invalid_date.status_code == 422
        assert "Invalid date range" in res_invalid_date.text

        # 6. Invalid timezone returns 422
        res_invalid_tz = client.post(
            "/api/v1/repositories/1/analyze",
            json={
                "scope": "all",
                "mode": "preset",
                "preset": "1m",
                "timezone": "Invalid/Timezone_Name",
            },
        )
        assert res_invalid_tz.status_code == 422
        assert "Invalid IANA timezone" in res_invalid_tz.text


def test_regression_background_jobs_scenario(monkeypatch):
    """Verify background job creation with scenario parameters."""
    app = create_app()
    user = _create_mock_user(user_id=1)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: MagicMock()

    from app.modules.analysis import router as analysis_router_mod

    fake_job = MagicMock()
    fake_job.id = "11111111-2222-3333-4444-555555555555"
    fake_job.repo_id = 1
    fake_job.scope = "full"
    fake_job.status = "queued"
    fake_job.progress = 0
    fake_job.step = "queued"
    fake_job.error_code = None
    fake_job.retry_of = None

    monkeypatch.setattr(
        analysis_router_mod.service,
        "create",
        MagicMock(return_value=(fake_job, True)),
    )
    monkeypatch.setattr(analysis_router_mod, "dispatch", MagicMock())

    with TestClient(app) as client:
        # Background job with repo_id and normalized scope
        res_job = client.post(
            "/api/v1/analysis/jobs",
            headers={"Origin": "http://localhost:5173"},
            json={
                "repo_id": 1,
                "scope": "all",
                "branch": "master",
                "mode": "custom",
                "start_date": "2026-11-09",
                "end_date": "2026-11-10",
                "timezone": "Asia/Ho_Chi_Minh",
            },
        )
        assert res_job.status_code == 202

        # Background job with repository_id alias
        res_alias = client.post(
            "/api/v1/analysis/jobs",
            headers={"Origin": "http://localhost:5173"},
            json={"repository_id": 1, "scope": "full"},
        )
        assert res_alias.status_code == 202

        # Background job without repo identifier returns 422
        res_missing_repo = client.post(
            "/api/v1/analysis/jobs",
            headers={"Origin": "http://localhost:5173"},
            json={"scope": "full"},
        )
        assert res_missing_repo.status_code == 422
