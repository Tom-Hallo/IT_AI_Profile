"""Fixture test PBI-017: SQLite in-memory + dữ liệu thật qua guard thật."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401  (đăng ký đủ model trên Base.metadata)
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
from app.modules.role_scoring.dependencies import get_skill_snapshot_source
from app.modules.users.models import User

SECRET_CONTENT = "SECRET_PRIVATE_SOURCE_aws_key_AKIA123"
SECRET_RATIONALE = "SECRET_RATIONALE_do_not_leak"
SHA = "a" * 40


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


class World:
    """Builder dữ liệu cho một kịch bản test."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._repo_seq = 0
        # BigInteger PK không tự tăng trên SQLite → gán id tường minh.
        self._user_seq = 0
        self._consent_seq = 0

    def user(self, email: str, *, private_enabled: bool = False) -> User:
        self._user_seq += 1
        user = User(
            id=self._user_seq, email=email, full_name=email, hashed_password="x"
        )
        self.db.add(user)
        self.db.flush()
        self.db.add(
            OAuthAccount(
                id=user.id,
                user_id=user.id,
                provider="github",
                provider_user_id=f"gh-{user.id}",
                encrypted_access_token="enc",
                scope="repo read:user" if private_enabled else "read:user",
                access_mode="private_enabled" if private_enabled else "public_only",
            )
        )
        self.db.commit()
        return user

    def repo(
        self, owner: User, *, private: bool = False, link: bool = True
    ) -> Repository:
        self._repo_seq += 1
        repo = Repository(
            owner_id=owner.id,
            external_id=f"ext-{self._repo_seq}",
            name=f"repo-{self._repo_seq}",
            html_url=f"https://example.test/{self._repo_seq}",
            private=private,
        )
        self.db.add(repo)
        self.db.flush()
        if link:
            self.db.execute(
                user_repository.insert().values(user_id=owner.id, repository_id=repo.id)
            )
        self.db.commit()
        return repo

    def consent(self, user: User, repo: Repository, *, revoked: bool = False) -> None:
        self._consent_seq += 1
        self.db.add(
            PrivateConsent(
                id=self._consent_seq,
                user_id=user.id,
                repository_id=repo.id,
                consent_type=ACCESS,
                provider_key="",
                policy_version=POLICY_VERSION,
                scope=["backend/"],
                granted=True,
                granted_at=datetime.now(UTC),
                revoked_at=datetime.now(UTC) if revoked else None,
            )
        )
        self.db.commit()

    def verification(
        self, user: User, repo: Repository, status: str = "verified"
    ) -> None:
        self.db.add(
            RepositoryVerification(
                repository_id=repo.id,
                user_id=user.id,
                verification_status=status,
                summary_data={},
                limitations=[],
            )
        )
        self.db.commit()

    def report(
        self,
        repo: Repository,
        evidence: list[tuple[str, str, str]],
        *,
        commit: str = SHA,
        confidence: float = 0.9,
    ) -> AnalysisReport:
        """evidence = [(classification, file_path, evidence_source)]."""
        report = AnalysisReport(
            repository_id=repo.id,
            commit_sha=commit,
            scope="all",
            structure={},
            languages=[],
            frameworks=[],
            architecture=[],
            budget={},
        )
        self.db.add(report)
        self.db.flush()
        for classification, path, source in evidence:
            self.db.add(
                AnalysisEvidence(
                    report_id=report.id,
                    repository_id=repo.id,
                    commit_sha=commit,
                    file_path=path,
                    finding_type="architecture",
                    classification=classification,
                    evidence_source=source,
                    detection_method="structural_inspection",
                    confidence="high",
                    confidence_score=confidence,
                    rationale=SECRET_RATIONALE,
                    line_number=7,
                    matched_content=SECRET_CONTENT,
                )
            )
        self.db.commit()
        return report


@pytest.fixture
def world(db) -> World:
    return World(db)


class StubSource:
    def __init__(self, raw=None, error: Exception | None = None) -> None:
        self.raw, self.error, self.calls = raw, error, 0

    def fetch(self, user_id, *, snapshot_ref=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.raw


@pytest.fixture
def make_client(db):
    clients: list[TestClient] = []

    def _make(user=None, source=None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_session] = lambda: db
        if user is not None:
            app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_skill_snapshot_source] = lambda: (
            source or StubSource(None)
        )
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.close()
