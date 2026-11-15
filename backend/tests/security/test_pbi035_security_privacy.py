"""Comprehensive Security, Privacy & Negative-Path Tests (PBI-035).

Bao quát toàn diện các mối đe doạ bảo mật & kịch bản negative:
1. Threat / Negative-path matrix cho OAuth, GitHub, AI Mentor, Scoring.
2. Kiểm tra chặt 401 Unauthorized (unauthenticated) & 403 Forbidden.
3. Thu hồi quyền (Revoked Consent) -> Ngay lập tức chặn truy cập private.
4. Chống rò rỉ dữ liệu nhạy cảm (matched_content, rationale bí mật, API token).
5. Xác minh dọn dẹp (cleanup) dữ liệu/code tạm khi revoke quyền hoặc job lỗi.
6. Chống tấn công SSRF & kiểm soát URL độc hại.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
import app.modules.consent.models  # noqa: F401
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.modules.analysis.models import (
    AnalysisEvidence,
    AnalysisReport,
    RepositoryVerification,
)
from app.modules.auth.models import OAuthAccount
from app.modules.consent.models import PrivateConsent
from app.modules.consent.service import ACCESS, POLICY_VERSION
from app.modules.github.models import Repository, user_repository
from app.modules.jobs.schemas import JDAnalysisRequest
from app.modules.jobs.service import JDAnalysisService
from app.modules.jobs.url_fetcher import SSRFBlockedError, validate_url_security
from app.modules.role_scoring.access import AccessDecision, DbRepositoryAccessGuard
from app.modules.role_scoring.skill_adapter import (
    RawSkillSnapshot,
    SkillSnapshotAdapter,
)
from app.modules.users.models import User

SECRET_API_TOKEN = "ghp_SECRET_TOKEN_DO_NOT_LEAK_1234567890abcdef"
SECRET_PRIVATE_SNIPPET = "AWS_SECRET_ACCESS_KEY=AKIA_SUPER_SECRET_12345"
SECRET_PRIVATE_RATIONALE = "RATIONALE_INTERNAL_DO_NOT_EXPOSE"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _attach(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS ita")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(bind=engine)


class SecurityFixtureBuilder:
    """Helper tạo dữ liệu test cô lập cho bảo mật."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._seq = 0

    def create_user(
        self, email: str, *, private_enabled: bool = False
    ) -> tuple[User, OAuthAccount]:
        self._seq += 1
        user = User(
            id=self._seq,
            email=email,
            full_name=f"User {self._seq}",
            hashed_password="pbkdf2_sha256$hashed",
        )
        self.session.add(user)
        self.session.flush()

        oauth = OAuthAccount(
            id=user.id,
            user_id=user.id,
            provider="github",
            provider_user_id=f"gh-{user.id}",
            encrypted_access_token=SECRET_API_TOKEN,
            scope="repo read:user" if private_enabled else "read:user",
            access_mode="private_enabled" if private_enabled else "public_only",
        )
        self.session.add(oauth)
        self.session.commit()
        return user, oauth

    def create_repo(
        self, owner: User, *, name: str, private: bool = False
    ) -> Repository:
        self._seq += 1
        repo = Repository(
            id=self._seq,
            owner_id=owner.id,
            external_id=f"ext-{self._seq}",
            name=name,
            html_url=f"https://github.com/test/{name}",
            private=private,
        )
        self.session.add(repo)
        self.session.flush()
        self.session.execute(
            user_repository.insert().values(user_id=owner.id, repository_id=repo.id)
        )
        self.session.commit()
        return repo

    def create_consent(
        self, user: User, repo: Repository, *, revoked: bool = False
    ) -> PrivateConsent:
        self._seq += 1
        consent = PrivateConsent(
            id=self._seq,
            user_id=user.id,
            repository_id=repo.id,
            consent_type=ACCESS,
            provider_key="github",
            policy_version=POLICY_VERSION,
            scope=["backend/"],
            granted=not revoked,
            granted_at=datetime.now(UTC),
            revoked_at=datetime.now(UTC) if revoked else None,
        )
        self.session.add(consent)
        self.session.commit()
        return consent

    def create_report_with_sensitive_evidence(self, repo: Repository) -> AnalysisReport:
        self._seq += 1
        report = AnalysisReport(
            id=self._seq,
            repository_id=repo.id,
            commit_sha="a" * 40,
            scope="all",
            structure={},
            languages=[],
            frameworks=[],
            architecture=[],
            budget={},
        )
        self.session.add(report)
        self.session.flush()

        evidence = AnalysisEvidence(
            report_id=report.id,
            repository_id=repo.id,
            commit_sha="a" * 40,
            file_path="secrets/config.py",
            finding_type="architecture",
            classification="api_service",
            evidence_source="source_code",
            detection_method="content_inspection",
            confidence="high",
            confidence_score=0.95,
            rationale=SECRET_PRIVATE_RATIONALE,
            line_number=42,
            matched_content=SECRET_PRIVATE_SNIPPET,
        )
        self.session.add(evidence)
        self.session.commit()
        return report


@pytest.fixture
def sec_builder(db: Session) -> SecurityFixtureBuilder:
    return SecurityFixtureBuilder(db)


def make_client_for_user(db: Session, user: User | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# =============================================================================
# 1. Negative-Path Authentication: 401 khi không đăng nhập
# =============================================================================


class TestAuthenticationNegativePaths:
    """Kiểm tra toàn bộ các endpoint bảo vệ từ chối khi thiếu xác thực (401)."""

    def test_unauthenticated_requests_return_401(self, db: Session):
        client = make_client_for_user(db, user=None)

        protected_endpoints = [
            ("GET", "/api/v1/github/repositories"),
            ("GET", "/api/v1/role-scoring/roles"),
            ("GET", "/api/v1/role-scoring/roles/backend_developer/score"),
            ("GET", "/api/v1/scoring/repositories/1/skills"),
            ("POST", "/api/v1/jobs/analyze"),
            ("GET", "/api/v1/mentor/sources"),
            ("GET", "/api/v1/repositories/1/consents"),
        ]

        for method, endpoint in protected_endpoints:
            if method == "GET":
                resp = client.get(endpoint)
            else:
                resp = client.post(endpoint, json={})
            assert resp.status_code == 401, f"{endpoint} không trả về 401"


# =============================================================================
# 2. Access Control & Cross-User Isolation (Chống truy cập chéo dữ liệu)
# =============================================================================


class TestAccessControlAndDataIsolation:
    """Người dùng A không được phép đọc hoặc can thiệp dữ liệu của Người dùng B."""

    def test_user_cannot_access_another_users_repository(
        self, db: Session, sec_builder: SecurityFixtureBuilder
    ):
        victim, _ = sec_builder.create_user("victim@sec.test")
        attacker, _ = sec_builder.create_user("attacker@sec.test")

        victim_repo = sec_builder.create_repo(
            victim, name="victim-private", private=True
        )
        sec_builder.create_report_with_sensitive_evidence(victim_repo)

        # Attacker cố gắng kiểm tra guard với repo của nạn nhân
        attacker_guard = DbRepositoryAccessGuard(db, attacker)
        decision = attacker_guard.check(victim_repo.id)
        assert decision == AccessDecision.NOT_FOUND

    def test_role_scoring_blocks_access_to_other_users_repo(
        self, db: Session, sec_builder: SecurityFixtureBuilder
    ):
        victim, _ = sec_builder.create_user("victim@sec.test")
        attacker, _ = sec_builder.create_user("attacker@sec.test")

        victim_repo = sec_builder.create_repo(victim, name="victim-secret-repo")
        sec_builder.create_report_with_sensitive_evidence(victim_repo)

        client = make_client_for_user(db, user=attacker)
        resp = client.get(
            "/api/v1/role-scoring/roles/backend_developer/score",
            params={"repository_id": victim_repo.id},
        )
        assert resp.status_code == 404
        assert victim_repo.name not in resp.text


# =============================================================================
# 3. Dual-Consent & Revocation: Thu hồi quyền lập tức chặn truy cập
# =============================================================================


class TestConsentEnforcementAndRevocation:
    """Kiểm tra luật Consent riêng tư và thu hồi quyền (PBI-007, PBI-008)."""

    def test_private_repo_without_consent_returns_403(
        self, db: Session, sec_builder: SecurityFixtureBuilder
    ):
        user, _ = sec_builder.create_user("dev@sec.test", private_enabled=True)
        repo = sec_builder.create_repo(user, name="internal-tool", private=True)
        sec_builder.create_report_with_sensitive_evidence(repo)

        guard = DbRepositoryAccessGuard(db, user)
        # Chưa cấp consent -> Private consent required
        assert guard.check(repo.id) == AccessDecision.PRIVATE_CONSENT_REQUIRED

        client = make_client_for_user(db, user=user)
        resp = client.get(
            "/api/v1/role-scoring/roles/backend_developer/score",
            params={"repository_id": repo.id},
        )
        assert resp.status_code == 403

    def test_revoked_consent_fails_closed_immediately(
        self, db: Session, sec_builder: SecurityFixtureBuilder
    ):
        user, _ = sec_builder.create_user("dev@sec.test", private_enabled=True)
        repo = sec_builder.create_repo(user, name="client-project", private=True)
        sec_builder.create_report_with_sensitive_evidence(repo)

        # Cấp consent rồi sau đó thu hồi
        sec_builder.create_consent(user, repo, revoked=True)

        guard = DbRepositoryAccessGuard(db, user)
        assert guard.check(repo.id) == AccessDecision.PRIVATE_CONSENT_REQUIRED

        client = make_client_for_user(db, user=user)
        resp = client.get(
            "/api/v1/role-scoring/roles/backend_developer/score",
            params={"repository_id": repo.id},
        )
        assert resp.status_code == 403

    def test_snapshot_referencing_revoked_repo_is_dropped_whole(
        self, db: Session, sec_builder: SecurityFixtureBuilder
    ):
        """Skill snapshot chứa repo đã bị revoke quyền phải bị loại bỏ hoàn toàn."""
        user, _ = sec_builder.create_user("dev@sec.test", private_enabled=True)
        repo = sec_builder.create_repo(user, name="revoked-repo", private=True)
        sec_builder.create_consent(user, repo, revoked=True)

        guard = DbRepositoryAccessGuard(db, user)
        raw_snapshot = RawSkillSnapshot(
            user.id,
            {
                "snapshot_ref": "snap-test",
                "repository_ids": [str(repo.id)],
                "items": [
                    {
                        "skill_key": "python",
                        "score": 90,
                        "confidence": 90,
                        "evidence_refs": [
                            {"repository_id": repo.id, "file_path": "a.py"}
                        ],
                    }
                ],
            },
        )

        class DummySource:
            def fetch(self, *a, **kw):
                return raw_snapshot

        adapter = SkillSnapshotAdapter(DummySource())
        result = adapter.load(user.id, guard=guard)
        # Toàn bộ snapshot bị loại bỏ để đảm bảo an toàn tuyệt đối
        assert result.status.value == "FORBIDDEN"
        assert result.snapshot is None


# =============================================================================
# 4. Leakage & Redaction: Không lộ secret/token/private code qua API, AI, Log
# =============================================================================


class TestDataRedactionAndNoLeakage:
    """Bảo đảm các trường nhạy cảm không bao giờ serialize ra JSON trả về."""

    def test_no_secrets_or_private_snippets_leaked_in_scoring_api(
        self, db: Session, sec_builder: SecurityFixtureBuilder
    ):
        user, _ = sec_builder.create_user("coder@sec.test", private_enabled=True)
        repo = sec_builder.create_repo(user, name="authorized-repo", private=True)
        sec_builder.create_consent(user, repo, revoked=False)
        sec_builder.session.add(
            RepositoryVerification(
                repository_id=repo.id,
                user_id=user.id,
                verification_status="verified",
                summary_data={},
                limitations=[],
            )
        )
        sec_builder.session.commit()
        sec_builder.create_report_with_sensitive_evidence(repo)

        client = make_client_for_user(db, user=user)
        resp = client.get(
            "/api/v1/role-scoring/roles/backend_developer/score",
            params={"repository_id": repo.id},
        )

        raw_response_text = resp.text
        # Tuyệt đối không xuất hiện các chuỗi nhạy cảm
        assert SECRET_API_TOKEN not in raw_response_text
        assert SECRET_PRIVATE_SNIPPET not in raw_response_text
        assert SECRET_PRIVATE_RATIONALE not in raw_response_text
        assert "matched_content" not in raw_response_text
        assert "line_number" not in raw_response_text


# =============================================================================
# 5. SSRF & Malicious Input Defense (Bảo vệ JD Analysis & URL Fetching)
# =============================================================================


class TestSSRFAndInputSanitization:
    """Kiểm tra phòng chống tấn công SSRF từ URL và input độc hại."""

    @pytest.mark.parametrize(
        "malicious_url",
        [
            "http://127.0.0.1:8000/",
            "http://localhost:5432/",
            "http://169.254.169.254/computeMetadata/v1/",
            "http://10.255.0.1/admin",
            "http://192.168.1.1/setup.cgi",
            "http://172.16.0.1/private",
            "file:///etc/shadow",
            "gopher://127.0.0.1:6379/_flushall",
        ],
    )
    def test_ssrf_urls_strictly_blocked(self, malicious_url: str):
        with pytest.raises(SSRFBlockedError):
            validate_url_security(malicious_url)

    def test_jd_service_handles_ssrf_attempt_safely(self):
        service = JDAnalysisService()
        req = JDAnalysisRequest(url="http://localhost:8080/internal-job")
        resp = service.analyze(req)

        # Không crash hệ thống, trả về fallback an toàn
        assert resp.total_skills_count == 0
        assert resp.fallback is not None
        assert resp.fallback.fallback_mode == "paste_text"


# =============================================================================
# 6. Source Cleanup & Failure Rollback Verification
# =============================================================================


class TestCleanupAndRollbackIntegrity:
    """Xác minh dọn dẹp dữ liệu tạm và rollback khi có lỗi hệ thống."""

    def test_cleanup_function_handles_empty_or_failed_job_gracefully(self):
        from app.modules.consent.cleanup_service import request_cleanup

        db_mock = MagicMock()
        db_mock.scalar.return_value = None  # không tìm thấy row cũ -> db.add

        job_mock = MagicMock()
        job_mock.id = "00000000-0000-0000-0000-000000000001"
        job_mock.user_id = 999
        job_mock.repo_id = 888

        request_cleanup(db_mock, job_mock, reason="consent_revoked")
        assert db_mock.add.called
