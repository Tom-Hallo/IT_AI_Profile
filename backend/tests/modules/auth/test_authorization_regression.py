"""Comprehensive regression test suite for GitHub Public/Private authorization.

Verifies:
1. Public-only with no historical private access.
2. Private-enabled with valid consent.
3. Private -> Disconnect -> Public-only (Primary reproduction scenario).
4. GitHub token retaining 'repo' scope does not bypass server-authoritative
   'public_only' access_mode.
5. Repository listing, pagination, and search filter out private repos
   in public_only mode.
6. Direct repository detail access returns 404 for private repos in public_only mode.
7. Sync status masks private repo count and timestamps in public_only mode.
8. PBI-010 Activity Analysis on private repo raises 403 when public_only.
9. PBI-012 Static Code Analysis on private repo raises 404 when public_only.
10. Historical analysis reports and evidence on private repo are inaccessible
    (404) when public_only.
11. Selection service enforces access mode.
12. Disconnect cleans up tokens, access_mode, active consents, sync cache,
    and analysis cache.
13. Worker task execution fails closed if private access is unauthorized.
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.modules.assessments.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.consent.cleanup_models  # noqa: F401
import app.modules.consent.models  # noqa: F401
import app.modules.cvs.models  # noqa: F401
import app.modules.github.models  # noqa: F401
import app.modules.roadmaps.models  # noqa: F401
import app.modules.users.models  # noqa: F401
from app.api.dependencies import get_current_user
from app.core.security import encrypt_token
from app.db.base import Base
from app.db.session import get_session
from app.modules.analysis.models import AnalysisEvidence, AnalysisReport
from app.modules.analysis.schemas import RepositoryAnalysisRequest
from app.modules.analysis.service import (
    _ANALYSIS_CACHE,
    analyze_repository,
    get_analysis_evidence,
    get_latest_analysis,
    verify_repository_access,
)
from app.modules.auth.models import OAuthAccount
from app.modules.auth.service import (
    consume_oauth_access_mode,
    consume_oauth_state,
    create_oauth_state,
    disconnect_github,
    has_private_access,
)
from app.modules.consent.models import PrivateConsent
from app.modules.github import router as github_router
from app.modules.github.models import Repository, user_repository
from app.modules.github.selection_service import credentials, options
from app.modules.github.service import get_user_sync_status
from app.modules.users.models import User
from app.services import activity


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


@pytest.fixture
def fake_redis(monkeypatch):
    store = {}

    class FakeRedisClient:
        def set(self, key, value, ex=None):
            store[key] = value
            return True

        def get(self, key):
            return store.get(key)

        def getdel(self, key):
            return store.pop(key, None)

        def delete(self, key):
            return 1 if store.pop(key, None) is not None else 0

    fake = FakeRedisClient()
    monkeypatch.setattr("app.modules.auth.service._get_redis", lambda: fake)
    monkeypatch.setattr("app.modules.github.service.get_redis_connection", lambda: fake)
    return fake


@pytest.fixture
def test_user(in_memory_db: Session) -> User:
    user = User(
        id=1,
        email="developer@example.com",
        full_name="Developer One",
        hashed_password="hashed_pw_placeholder",
    )
    in_memory_db.add(user)
    in_memory_db.commit()
    return user


@pytest.fixture
def setup_user_repositories(in_memory_db: Session, test_user: User):
    """Tạo 1 public repo và 1 private repo gắn với user."""
    public_repo = Repository(
        id=10,
        owner_id=test_user.id,
        external_id="ext-pub-10",
        name="public-repo",
        full_name="developer/public-repo",
        html_url="https://github.com/developer/public-repo",
        description="Public Repository",
        private=False,
        default_branch="main",
        pushed_at=datetime(2026, 11, 8, tzinfo=UTC),
        last_synced_at=datetime(2026, 11, 8, tzinfo=UTC),
        sync_status="synced",
    )
    private_repo = Repository(
        id=20,
        owner_id=test_user.id,
        external_id="ext-priv-20",
        name="private-repo",
        full_name="developer/private-repo",
        html_url="https://github.com/developer/private-repo",
        description="Confidential Private Repository",
        private=True,
        default_branch="main",
        pushed_at=datetime(2026, 11, 9, tzinfo=UTC),
        last_synced_at=datetime(2026, 11, 9, tzinfo=UTC),
        sync_status="synced",
    )
    in_memory_db.add_all([public_repo, private_repo])
    in_memory_db.flush()

    in_memory_db.execute(
        user_repository.insert(),
        [
            {
                "user_id": test_user.id,
                "repository_id": public_repo.id,
                "added_at": datetime(2026, 11, 8, tzinfo=UTC),
            },
            {
                "user_id": test_user.id,
                "repository_id": private_repo.id,
                "added_at": datetime(2026, 11, 9, tzinfo=UTC),
            },
        ],
    )
    in_memory_db.commit()
    return public_repo, private_repo


@pytest.fixture
def client(in_memory_db: Session, test_user: User):
    app = FastAPI()
    app.include_router(github_router.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_session] = lambda: in_memory_db
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1. OAuth State & Access Mode Flow
# -----------------------------------------------------------------------------


def test_oauth_state_and_access_mode_persistence(fake_redis):
    """Xác minh luồng tạo và tiêu thụ OAuth state cùng access_mode."""
    # Test wrong binding fails and consumes invalid attempt
    state1 = create_oauth_state("browser-xyz", access_mode="private_enabled")
    assert isinstance(state1, str)
    assert len(state1) > 20
    assert consume_oauth_state(state1, "wrong-binding") is False
    assert consume_oauth_state(state1, "browser-xyz") is False

    # Test correct binding consumes state once
    state2 = create_oauth_state("browser-xyz", access_mode="private_enabled")
    assert consume_oauth_state(state2, "browser-xyz") is True
    # Replay fails
    assert consume_oauth_state(state2, "browser-xyz") is False

    # Access mode retrieved
    mode = consume_oauth_access_mode(state2)
    assert mode == "private_enabled"

    # Secondary consumption returns default 'public_only'
    assert consume_oauth_access_mode(state2) == "public_only"


# -----------------------------------------------------------------------------
# 2. Centralized has_private_access Authorization Matrix
# -----------------------------------------------------------------------------


def test_has_private_access_evaluation_matrix(in_memory_db: Session, test_user: User):
    """Kiểm tra ma trận quyền truy cập fail-closed của has_private_access."""
    # Scenario A: Chưa có OAuthAccount
    assert has_private_access(in_memory_db, test_user.id) is False

    # Scenario B: Có OAuthAccount nhưng không có token (đã disconnect)
    oauth = OAuthAccount(
        id=101,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=None,
        scope="read:user repo",
        access_mode="private_enabled",
    )
    in_memory_db.add(oauth)
    in_memory_db.commit()
    assert has_private_access(in_memory_db, test_user.id) is False

    # Scenario C: Có token, scope có 'repo', nhưng access_mode là 'public_only'
    # (Trường hợp then chốt: GitHub token giữ lại scope từ trước)
    oauth.encrypted_access_token = encrypt_token("gho_valid_token")
    oauth.access_mode = "public_only"
    oauth.scope = "read:user user:email repo"
    in_memory_db.commit()
    assert has_private_access(in_memory_db, test_user.id) is False

    # Scenario D: access_mode là 'private_enabled' nhưng scope thiếu 'repo'
    oauth.access_mode = "private_enabled"
    oauth.scope = "read:user user:email"
    in_memory_db.commit()
    assert has_private_access(in_memory_db, test_user.id) is False

    # Scenario E: Đầy đủ điều kiện (token hợp lệ + private_enabled + scope có repo)
    oauth.scope = "read:user user:email repo"
    in_memory_db.commit()
    assert has_private_access(in_memory_db, test_user.id) is True

    # Scenario F: Thuộc tính bất thường (ví dụ: full_name) không được phép bypass
    oauth.access_mode = "public_only"
    oauth.full_name = "Privileged User"  # type: ignore[attr-defined]
    in_memory_db.commit()
    assert has_private_access(in_memory_db, test_user.id) is False


# -----------------------------------------------------------------------------
# 3. Primary Reproduction: Private -> Disconnect -> Reconnect Public-Only
# -----------------------------------------------------------------------------


def test_reconnect_public_only_prevents_private_repo_access(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    client: TestClient,
    fake_redis,
):
    """Tái hiện và xác minh sửa lỗi hồi quy:

    1. Kết nối Private -> Đồng bộ cả repo public và private.
    2. Ngắt kết nối (Disconnect).
    3. Kết nối lại chọn Public-only (kể cả khi GitHub trả về scope có 'repo').
    4. Repo private lịch sử KHÔNG ĐƯỢC PHÉP xuất hiện trong danh sách, tìm kiếm,
       chi tiết, hoặc sync status.
    """
    public_repo, private_repo = setup_user_repositories

    # Bước 1: Tài khoản đã kết nối với Private access
    oauth = OAuthAccount(
        id=102,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_initial_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    in_memory_db.add(oauth)
    in_memory_db.commit()

    # Trong chế độ private_enabled: cả 2 repos đều hiển thị
    res = client.get("/api/v1/github/repositories?visibility=all")
    assert res.status_code == 200
    assert res.json()["total"] == 2
    repo_ids = [r["id"] for r in res.json()["items"]]
    assert public_repo.id in repo_ids
    assert private_repo.id in repo_ids

    # Bước 2: Ngắt kết nối GitHub
    disconnected = disconnect_github(in_memory_db, test_user.id)
    assert disconnected is True
    assert oauth.encrypted_access_token is None
    assert oauth.access_mode == "public_only"

    # Bước 3: Người dùng kết nối lại và chọn Public-only
    # Giả lập GitHub trả về token vẫn chứa scope "repo" (do app auth cũ trên GitHub)
    oauth.encrypted_access_token = encrypt_token("gho_new_token")
    oauth.scope = "read:user user:email repo"
    oauth.access_mode = "public_only"
    in_memory_db.commit()

    # Bước 4: Kiểm tra nghiêm ngặt quyền truy cập

    # 4A. Repository Listing (visibility=all) chỉ trả về public repo
    res_all = client.get("/api/v1/github/repositories?visibility=all")
    assert res_all.status_code == 200
    assert res_all.json()["total"] == 1
    assert res_all.json()["items"][0]["id"] == public_repo.id
    assert res_all.json()["items"][0]["private"] is False

    # 4B. Repository Listing (visibility=public)
    res_pub = client.get("/api/v1/github/repositories?visibility=public")
    assert res_pub.status_code == 200
    assert res_pub.json()["total"] == 1
    assert res_pub.json()["items"][0]["id"] == public_repo.id

    # 4C. Repository Listing (visibility=private) KHÔNG ĐƯỢC trả về repo private
    res_priv = client.get("/api/v1/github/repositories?visibility=private")
    assert res_priv.status_code == 200
    assert res_priv.json()["total"] == 0
    assert len(res_priv.json()["items"]) == 0

    # 4D. Tìm kiếm bằng từ khóa của private repo không được trả về kết quả
    res_search = client.get("/api/v1/github/repositories?search=Confidential")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 0

    # 4E. Truy vấn trực tiếp detail endpoint của private repo phải trả về 404
    res_detail = client.get(f"/api/v1/github/repositories/{private_repo.id}")
    assert res_detail.status_code == 404
    assert "Không tìm thấy repository" in res_detail.json()["detail"]

    # Detail của public repo vẫn hoạt động bình thường
    res_pub_detail = client.get(f"/api/v1/github/repositories/{public_repo.id}")
    assert res_pub_detail.status_code == 200
    assert res_pub_detail.json()["id"] == public_repo.id


# -----------------------------------------------------------------------------
# 4. Sync Status Isolation
# -----------------------------------------------------------------------------


def test_reconnect_public_only_sync_status_isolated(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    client: TestClient,
    fake_redis,
):
    """Xác minh /github/sync/status không để rò rỉ số lượng hay thời gian sync của
    private repo.
    """
    public_repo, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=103,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="public_only",  # Người dùng chọn Public-only
    )
    in_memory_db.add(oauth)
    in_memory_db.commit()

    status_resp = get_user_sync_status(in_memory_db, test_user.id)
    assert status_resp["is_connected"] is True
    assert status_resp["has_private_scope"] is False  # Phải là False!
    assert status_resp["total_repositories"] == 1  # Chỉ tính public repo
    assert status_resp["last_synced_at"] == public_repo.last_synced_at.isoformat()


# -----------------------------------------------------------------------------
# 5. M-02 Activity Analysis Access Enforcement
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_activity_analysis_blocked_on_private_repo_in_public_mode(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Xác minh M-02 Activity Analysis từ chối phân tích repo private khi ở chế
    độ public_only.
    """
    public_repo, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=104,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="public_only",
    )
    in_memory_db.add(oauth)
    in_memory_db.commit()

    start = datetime(2026, 11, 1, tzinfo=UTC)
    end = datetime(2026, 11, 10, tzinfo=UTC)

    # Phân tích private repo phải bị chặn với 403
    with pytest.raises(HTTPException) as exc_info:
        await activity.analyze(
            in_memory_db,
            repository_id=private_repo.id,
            user_id=test_user.id,
            start=start,
            end=end,
        )
    assert exc_info.value.status_code == 403
    assert "Private repository analysis requires active private authorization" in (
        exc_info.value.detail
    )


# -----------------------------------------------------------------------------
# 6. M-03 Static Code Analysis & Evidence Protection
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_static_analysis_and_evidence_blocked_on_private_repo(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
):
    """Xác minh M-03 Static Code Analysis, báo cáo lịch sử và bằng chứng
    của private repo bị chặn (404) khi ở chế độ public_only.
    """
    public_repo, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=105,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="public_only",
    )
    in_memory_db.add(oauth)

    # Tạo sẵn báo cáo và bằng chứng lịch sử cho private repo
    report = AnalysisReport(
        id=201,
        repository_id=private_repo.id,
        commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        analyzed_at=datetime(2026, 11, 9, tzinfo=UTC),
        scope="all",
        structure={"total_files": 10},
        languages={"Python": 100},
        frameworks=["FastAPI"],
        architecture={"style": "modular"},
        budget={"files_inspected": 10},
    )
    in_memory_db.add(report)
    in_memory_db.flush()

    evidence = AnalysisEvidence(
        id=301,
        report_id=report.id,
        repository_id=private_repo.id,
        commit_sha=report.commit_sha,
        file_path="secret/core.py",
        finding_type="framework",
        classification="FastAPI",
        evidence_source="imports",
        detection_method="ast",
        confidence="high",
        confidence_score=1.0,
        rationale="import fastapi detected",
    )
    in_memory_db.add(evidence)
    in_memory_db.commit()

    # 6A. verify_repository_access trên private repo trả về 404
    with pytest.raises(HTTPException) as exc_404:
        verify_repository_access(in_memory_db, private_repo.id, test_user)
    assert exc_404.value.status_code == 404

    # 6B. Phân tích tĩnh mới trên private repo trả về 404
    req = RepositoryAnalysisRequest(scope="all")
    with pytest.raises(HTTPException) as exc_an:
        await analyze_repository(in_memory_db, private_repo.id, test_user, req)
    assert exc_an.value.status_code == 404

    # 6C. Đọc kết quả phân tích lịch sử trả về 404
    with pytest.raises(HTTPException) as exc_rep:
        get_latest_analysis(in_memory_db, private_repo.id, test_user)
    assert exc_rep.value.status_code == 404

    # 6D. Đọc bằng chứng lịch sử trả về 404
    with pytest.raises(HTTPException) as exc_ev:
        get_analysis_evidence(in_memory_db, private_repo.id, test_user)
    assert exc_ev.value.status_code == 404


# -----------------------------------------------------------------------------
# 7. Selection Service Enforcement
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_selection_service_enforces_access_mode(
    in_memory_db: Session,
    test_user: User,
    monkeypatch,
):
    """Xác minh Selection Service (PBI-006) tuân thủ server-authoritative
    access_mode.
    """
    oauth = OAuthAccount(
        id=106,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="public_only",
    )
    in_memory_db.add(oauth)
    in_memory_db.commit()

    # credentials trả về private_access = False
    token, priv_access = credentials(in_memory_db, test_user.id)
    assert token == "gho_token"
    assert priv_access is False

    # Yêu cầu scope 'private' bị chặn với 403
    with pytest.raises(HTTPException) as exc_priv:
        await options(in_memory_db, test_user.id, scope="private")
    assert exc_priv.value.status_code == 403


# -----------------------------------------------------------------------------
# 8. Hardened Disconnect Cleanup
# -----------------------------------------------------------------------------


def test_disconnect_github_comprehensive_cleanup(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    fake_redis,
):
    """Xác minh disconnect_github thu hồi toàn bộ tokens, quyền riêng tư,
    cache sync và analysis.
    """
    public_repo, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=107,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    in_memory_db.add(oauth)

    # Thêm active consent
    consent = PrivateConsent(
        id=401,
        user_id=test_user.id,
        repository_id=private_repo.id,
        consent_type="repository_access",
        provider_key="",
        scope=["src/"],
        granted=True,
        policy_version="2.0",
        granted_at=datetime(2026, 11, 8, tzinfo=UTC),
        revoked_at=None,
    )
    in_memory_db.add(consent)
    in_memory_db.commit()

    # Set cache in Redis and memory
    fake_redis.set(f"ita:github:sync:{test_user.id}", '{"status": "completed"}')
    _ANALYSIS_CACHE[(private_repo.id, "sha123")] = {"data": "cached"}

    # Thực hiện disconnect
    disconnected = disconnect_github(in_memory_db, test_user.id)
    assert disconnected is True

    # 1. OAuthAccount tokens and mode reset
    assert oauth.encrypted_access_token is None
    assert oauth.scope is None
    assert oauth.access_mode == "public_only"

    # 2. PrivateConsent revoked
    in_memory_db.refresh(consent)
    assert consent.granted is False
    assert consent.revoked_at is not None

    # 3. Redis sync cache deleted
    assert fake_redis.get(f"ita:github:sync:{test_user.id}") is None

    # 4. In-memory analysis cache cleared for user's repos
    assert (private_repo.id, "sha123") not in _ANALYSIS_CACHE


# -----------------------------------------------------------------------------
# 9. Background Worker Task Revocation Enforcement
# -----------------------------------------------------------------------------


def test_worker_task_fails_closed_when_access_mode_public_only(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Xác minh worker task RQ fail-closed nếu job phân tích private repo chạy

    khi access_mode là public_only.
    """
    import uuid

    from app.modules.analysis.models import AnalysisJob
    from app.workers.tasks.analysis import run_analysis

    _, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=108,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="public_only",  # Quyền private không được cấp
    )
    in_memory_db.add(oauth)

    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        user_id=test_user.id,
        repo_id=private_repo.id,
        scope="all",
        status="queued",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    class FakeSessionScope:
        def __enter__(self):
            return in_memory_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    monkeypatch.setattr("app.workers.tasks.analysis.event", lambda _db, _j, _c: None)

    with pytest.raises(PermissionError) as exc_info:
        run_analysis(job_id=str(job_id))
    assert "Private repository access is not authorized" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 10. Sync Ingestion Masking in Public-Only Mode
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sync_repositories_filters_private_when_public_only(
    in_memory_db: Session,
    test_user: User,
    fake_redis,
):
    """Xác minh sync trong chế độ public_only không lưu hay liên kết private repos."""
    import httpx
    from sqlalchemy import select

    from app.modules.github.client import GitHubApiClient
    from app.modules.github.models import Repository
    from app.modules.github.service import sync_repositories_for_user

    oauth = OAuthAccount(
        id=109,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="public_only",
    )
    in_memory_db.add(oauth)
    in_memory_db.commit()

    fake_repos = [
        {
            "id": 9001,
            "name": "new-public",
            "full_name": "developer/new-public",
            "html_url": "https://github.com/developer/new-public",
            "description": "Public",
            "private": False,
            "default_branch": "main",
            "fork": False,
            "size": 100,
            "owner": {"login": "developer"},
        },
        {
            "id": 9002,
            "name": "new-private",
            "full_name": "developer/new-private",
            "html_url": "https://github.com/developer/new-private",
            "description": "Private",
            "private": True,
            "default_branch": "main",
            "fork": False,
            "size": 200,
            "owner": {"login": "developer"},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/languages" in url_str:
            return httpx.Response(200, json={"Python": 100})
        if "visibility=public" in url_str:
            return httpx.Response(200, json=[fake_repos[0]])
        return httpx.Response(200, json=fake_repos)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GitHubApiClient("test-token", client=mock_client)

    res = await sync_repositories_for_user(in_memory_db, test_user, client=client)
    assert res["status"] == "completed"
    assert res["synced_count"] == 1

    persisted_ext_ids = in_memory_db.scalars(
        select(Repository.external_id).where(
            Repository.external_id.in_(["9001", "9002"])
        )
    ).all()
    assert "9001" in persisted_ext_ids
    assert "9002" not in persisted_ext_ids


# -----------------------------------------------------------------------------
# 11. Disconnect GitHub Cancels In-Flight Private Repo Analysis Jobs
# -----------------------------------------------------------------------------


def test_disconnect_github_cancels_active_private_repo_jobs(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    fake_redis,
):
    """Xác minh disconnect_github cập nhật private repo jobs thành cancel_requested."""
    import uuid

    from app.modules.analysis.models import AnalysisJob
    from app.modules.auth.service import disconnect_github

    public_repo, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=110,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    in_memory_db.add(oauth)

    # Job for private repo (should be cancelled)
    private_job = AnalysisJob(
        id=uuid.uuid4(),
        user_id=test_user.id,
        repo_id=private_repo.id,
        scope="all",
        status="running",
    )
    # Job for public repo (should remain unaffected)
    public_job = AnalysisJob(
        id=uuid.uuid4(),
        user_id=test_user.id,
        repo_id=public_repo.id,
        scope="all",
        status="running",
    )
    in_memory_db.add_all([private_job, public_job])
    in_memory_db.commit()

    disconnect_github(in_memory_db, test_user.id)

    in_memory_db.refresh(private_job)
    in_memory_db.refresh(public_job)
    assert private_job.status == "cancel_requested"
    assert public_job.status == "running"


# -----------------------------------------------------------------------------
# 12. Pre-Persistence Gate Blocks Private Result Saving on Revocation
# -----------------------------------------------------------------------------


def test_worker_task_revalidates_and_aborts_persistence_if_permission_revoked(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Xác minh worker task kiểm tra lại quyền riêng tư trước khi lưu kết quả.

    Nếu user bị thu hồi quyền trong khi đang phân tích, worker phải raise
    PermissionError và không lưu AnalysisReport hay AnalysisEvidence.
    """
    import uuid

    from sqlalchemy import select

    from app.modules.analysis.inspector import InMemoryContentSource
    from app.modules.analysis.models import AnalysisJob, AnalysisReport
    from app.modules.consent.models import PrivateConsent
    from app.workers.tasks.analysis import run_analysis

    _, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=111,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    consent = PrivateConsent(
        id=402,
        user_id=test_user.id,
        repository_id=private_repo.id,
        consent_type="repository_access",
        provider_key="",
        scope=["src/"],
        granted=True,
        policy_version="2.0",
    )
    in_memory_db.add_all([oauth, consent])

    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        user_id=test_user.id,
        repo_id=private_repo.id,
        scope="all",
        status="queued",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    class FakeSessionScope:
        def __enter__(self):
            return in_memory_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    monkeypatch.setattr("app.workers.tasks.analysis.event", lambda _db, _j, _c: None)

    class RevokingContentSource(InMemoryContentSource):
        async def get_tree_items(self):
            # Giả lập sự kiện người dùng disconnect hoặc downgrade giữa lúc chạy
            oauth.access_mode = "public_only"
            in_memory_db.commit()
            return await super().get_tree_items()

    source = RevokingContentSource({"requirements.txt": "fastapi>=0.100.0"})

    with pytest.raises(PermissionError) as exc_info:
        run_analysis(job_id=str(job_id), custom_source=source)

    assert "Private repository access was revoked" in str(exc_info.value)

    # Báo cáo phân tích nhạy cảm không được phép lưu vào database
    reports = in_memory_db.scalars(
        select(AnalysisReport).where(AnalysisReport.repository_id == private_repo.id)
    ).all()
    assert len(reports) == 0


# -----------------------------------------------------------------------------
# 13. Missing PrivateConsent Blocks Worker Execution
# -----------------------------------------------------------------------------


def test_worker_task_fails_closed_when_private_consent_missing(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Xác minh worker task fail-closed nếu thiếu PrivateConsent hợp lệ."""
    import uuid

    from app.modules.analysis.models import AnalysisJob
    from app.workers.tasks.analysis import run_analysis

    _, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=112,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    in_memory_db.add(oauth)

    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        user_id=test_user.id,
        repo_id=private_repo.id,
        scope="all",
        status="queued",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    class FakeSessionScope:
        def __enter__(self):
            return in_memory_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                in_memory_db.commit()

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    monkeypatch.setattr("app.workers.tasks.analysis.event", lambda _db, _j, _c: None)

    with pytest.raises(PermissionError) as exc_info:
        run_analysis(job_id=str(job_id))

    assert "Private repository consent" in str(exc_info.value)
    in_memory_db.refresh(job)
    assert job.status == "failed"
    assert job.error_code == "PermissionError"


# -----------------------------------------------------------------------------
# 14. Revoked PrivateConsent Blocks Worker Execution
# -----------------------------------------------------------------------------


def test_worker_task_fails_closed_when_private_consent_revoked(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Xác minh worker task fail-closed nếu PrivateConsent đã bị thu hồi."""
    import uuid

    from app.modules.analysis.models import AnalysisJob
    from app.modules.consent.models import PrivateConsent
    from app.workers.tasks.analysis import run_analysis

    _, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=113,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    # Consent đã bị thu hồi
    consent = PrivateConsent(
        id=403,
        user_id=test_user.id,
        repository_id=private_repo.id,
        consent_type="repository_access",
        provider_key="",
        scope=["src/"],
        granted=False,
        policy_version="2.0",
        revoked_at=datetime(2026, 11, 9, tzinfo=UTC),
    )
    in_memory_db.add_all([oauth, consent])

    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        user_id=test_user.id,
        repo_id=private_repo.id,
        scope="all",
        status="queued",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    class FakeSessionScope:
        def __enter__(self):
            return in_memory_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                in_memory_db.commit()

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    monkeypatch.setattr("app.workers.tasks.analysis.event", lambda _db, _j, _c: None)

    with pytest.raises(PermissionError) as exc_info:
        run_analysis(job_id=str(job_id))

    assert "Private repository consent" in str(exc_info.value)
    in_memory_db.refresh(job)
    assert job.status == "failed"
    assert job.error_code == "PermissionError"


# -----------------------------------------------------------------------------
# 15. Cleanup Failures Are Logged and Queued in Outbox
# -----------------------------------------------------------------------------


def test_worker_task_cleanup_failure_logged_and_queued_in_outbox(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Xác minh lỗi dọn dẹp thư mục tạm thời được ghi nhận vào outbox để xử lý lại."""
    import uuid

    from app.modules.analysis.inspector import InMemoryContentSource
    from app.modules.analysis.models import AnalysisJob
    from app.modules.consent.cleanup_models import CleanupRequest
    from app.modules.consent.models import PrivateConsent
    from app.workers.tasks.analysis import run_analysis

    _, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=114,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    consent = PrivateConsent(
        id=404,
        user_id=test_user.id,
        repository_id=private_repo.id,
        consent_type="repository_access",
        provider_key="",
        scope=["src/"],
        granted=True,
        policy_version="2.0",
    )
    in_memory_db.add_all([oauth, consent])

    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        user_id=test_user.id,
        repo_id=private_repo.id,
        scope="all",
        status="queued",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    class FakeSessionScope:
        def __enter__(self):
            return in_memory_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                in_memory_db.commit()

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    monkeypatch.setattr("app.workers.tasks.analysis.event", lambda _db, _j, _c: None)

    # Giả lập lỗi dọn dẹp thư mục tạm
    def mock_failing_purge(_jid):
        raise OSError("Permission denied on disk")

    monkeypatch.setattr(
        "app.modules.consent.cleanup.purge_job_directory", mock_failing_purge
    )

    source = InMemoryContentSource({"requirements.txt": "fastapi>=0.100.0"})
    result = run_analysis(job_id=str(job_id), custom_source=source)
    assert result is not None

    # Xác minh CleanupRequest được tạo trong outbox
    cleanup_req = in_memory_db.scalar(
        select(CleanupRequest).where(CleanupRequest.job_id == job_id)
    )
    assert cleanup_req is not None
    assert cleanup_req.status == "pending"
    assert cleanup_req.reason == "cleanup_error"


# -----------------------------------------------------------------------------
# 16. Authorized Private Repo Analysis Executes and Persists Successfully
# -----------------------------------------------------------------------------


def test_authorized_private_repo_analysis_succeeds(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Xác minh phân tích repo private thành công khi có đủ quyền và consent."""
    import uuid

    from app.modules.analysis.inspector import InMemoryContentSource
    from app.modules.analysis.models import AnalysisJob, AnalysisReport
    from app.modules.consent.models import PrivateConsent
    from app.workers.tasks.analysis import run_analysis

    _, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=115,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    consent = PrivateConsent(
        id=405,
        user_id=test_user.id,
        repository_id=private_repo.id,
        consent_type="repository_access",
        provider_key="",
        scope=["src/"],
        granted=True,
        policy_version="2.0",
    )
    in_memory_db.add_all([oauth, consent])

    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        user_id=test_user.id,
        repo_id=private_repo.id,
        scope="all",
        status="queued",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    class FakeSessionScope:
        def __enter__(self):
            return in_memory_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                in_memory_db.commit()

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    monkeypatch.setattr("app.workers.tasks.analysis.event", lambda _db, _j, _c: None)

    source = InMemoryContentSource(
        {
            "requirements.txt": "fastapi>=0.110.0\nuvicorn>=0.28.0",
            "main.py": "from fastapi import FastAPI\napp = FastAPI()",
        }
    )

    result = run_analysis(
        job_id=str(job_id),
        custom_source=source,
        custom_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
    )
    assert result is not None
    assert result["repository_id"] == private_repo.id
    assert len(result["frameworks"]) > 0

    in_memory_db.refresh(job)
    assert job.status == "succeeded"
    assert job.progress == 100

    report = in_memory_db.scalar(
        select(AnalysisReport).where(AnalysisReport.repository_id == private_repo.id)
    )
    assert report is not None
    assert report.commit_sha == "abcdef1234567890abcdef1234567890abcdef12"


# -----------------------------------------------------------------------------
# 17. Disconnect GitHub Transactional Consistency and Rollback on DB Error
# -----------------------------------------------------------------------------


def test_disconnect_github_database_failure_rolls_back_and_raises(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Xác minh disconnect_github rollback toàn bộ và raise lỗi khi DB thất bại."""
    from sqlalchemy.exc import OperationalError

    from app.modules.auth.service import disconnect_github

    _, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=116,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    in_memory_db.add(oauth)
    in_memory_db.commit()

    # Giả lập lỗi database khi commit transaction disconnect
    def failing_commit():
        raise OperationalError("connection lost", {}, Exception("DB down"))

    monkeypatch.setattr(in_memory_db, "commit", failing_commit)

    with pytest.raises(OperationalError):
        disconnect_github(in_memory_db, test_user.id)

    # Khôi phục commit và kiểm tra trạng thái rollback
    monkeypatch.undo()
    in_memory_db.rollback()
    in_memory_db.refresh(oauth)
    # Vì rollback nên access_mode vẫn là trạng thái ban đầu, không bị lưu dở dang
    assert oauth.access_mode == "private_enabled"
    assert oauth.encrypted_access_token is not None


# -----------------------------------------------------------------------------
# 18. Worker Revocation Race — Job Cancelled Right Before Persistence
# -----------------------------------------------------------------------------


def test_worker_revocation_race_job_cancelled_before_persistence(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Xác minh worker không lưu kết quả nếu disconnect_github hủy job trước khi
    lưu kết quả.
    """
    import uuid

    from app.modules.analysis.inspector import InMemoryContentSource
    from app.modules.analysis.models import AnalysisJob, AnalysisReport
    from app.modules.consent.models import PrivateConsent
    from app.workers.tasks.analysis import run_analysis

    _, private_repo = setup_user_repositories

    oauth = OAuthAccount(
        id=117,
        user_id=test_user.id,
        provider="github",
        provider_user_id="111",
        encrypted_access_token=encrypt_token("gho_token"),
        scope="read:user repo",
        access_mode="private_enabled",
    )
    consent = PrivateConsent(
        id=406,
        user_id=test_user.id,
        repository_id=private_repo.id,
        consent_type="repository_access",
        provider_key="",
        scope=["src/"],
        granted=True,
        policy_version="2.0",
    )
    in_memory_db.add_all([oauth, consent])

    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        user_id=test_user.id,
        repo_id=private_repo.id,
        scope="all",
        status="queued",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    class FakeSessionScope:
        def __enter__(self):
            return in_memory_db

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                in_memory_db.commit()

    monkeypatch.setattr("app.db.session.session_scope", FakeSessionScope)
    monkeypatch.setattr("app.workers.tasks.analysis.event", lambda _db, _j, _c: None)

    class ConcurrentlyCancelledSource(InMemoryContentSource):
        async def get_tree_items(self):
            # Giả lập disconnect_github chạy đồng thời trong lúc worker đang đọc code
            job.status = "cancel_requested"
            in_memory_db.commit()
            return await super().get_tree_items()

    source = ConcurrentlyCancelledSource(
        {"requirements.txt": "fastapi>=0.110.0\nuvicorn>=0.28.0"}
    )

    result = run_analysis(job_id=str(job_id), custom_source=source)
    # Worker bị hủy và trả về None
    assert result is None

    in_memory_db.refresh(job)
    assert job.status == "cancelled"

    # Kết quả phân tích nhạy cảm không được lưu
    report = in_memory_db.scalar(
        select(AnalysisReport).where(AnalysisReport.repository_id == private_repo.id)
    )
    assert report is None


def test_f07_report_verification_evidence_rollback_together(
    in_memory_db: Session,
    test_user: User,
    setup_user_repositories,
    monkeypatch,
):
    """Rollback phải xóa cả report, verification và evidence chưa commit."""
    from sqlalchemy.orm import sessionmaker

    from app.db.session import session_scope
    from app.modules.analysis.models import (
        AnalysisReport,
        RepositoryVerification,
        VerificationEvidence,
    )
    from app.modules.analysis.service import (
        _ANALYSIS_CACHE,
        save_analysis_result,
    )

    public_repo, _ = setup_user_repositories
    commit_sha = "f" * 40

    # Dùng session thật, có commit/rollback.
    test_session_factory = sessionmaker(
        bind=in_memory_db.get_bind(),
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        "app.db.session.SessionLocal",
        test_session_factory,
    )

    result = {
        "repository_id": public_repo.id,
        "commit_sha": commit_sha,
        "scope": "all",
        "structure": {},
        "languages": [],
        "frameworks": [],
        "architecture": [],
        "budget": {},
        "evidence": [],
    }

    with pytest.raises(RuntimeError, match="forced rollback"):
        with session_scope() as db:
            report = save_analysis_result(
                db,
                result,
                commit=False,
            )

            assert report is not None
            assert report.id is not None

            verification = RepositoryVerification(
                repository_id=public_repo.id,
                user_id=test_user.id,
                report_id=report.id,
                verification_status="unknown",
                coverage_status="partial",
                confidence="uncertain",
            )
            db.add(verification)
            db.flush()

            evidence = VerificationEvidence(
                verification_id=verification.id,
                repository_id=public_repo.id,
                user_id=test_user.id,
                evidence_type="commit",
                target_identifier=commit_sha,
                verification_status="unknown",
                rationale="Test rollback",
            )
            db.add(evidence)
            db.flush()

            # Giả lập lỗi trước khi transaction commit.
            raise RuntimeError("forced rollback")

    with session_scope() as db:
        assert (
            db.scalar(
                select(AnalysisReport).where(AnalysisReport.commit_sha == commit_sha)
            )
            is None
        )

        assert (
            db.scalar(
                select(RepositoryVerification).where(
                    RepositoryVerification.repository_id == public_repo.id
                )
            )
            is None
        )

        assert (
            db.scalar(
                select(VerificationEvidence).where(
                    VerificationEvidence.target_identifier == commit_sha
                )
            )
            is None
        )

    # Report thất bại cũng không được xuất hiện trong cache.
    assert not any(
        key[0] == public_repo.id and key[1] == commit_sha for key in _ANALYSIS_CACHE
    )
