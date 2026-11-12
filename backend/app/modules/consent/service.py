"""PBI-007: server-authoritative, fail-closed double consent."""

from datetime import UTC, datetime
from pathlib import PurePosixPath

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.analysis.models import ACTIVE, AnalysisJob
from app.modules.consent.cleanup_service import request_cleanup
from app.modules.consent.models import PrivateConsent, PrivateConsentAudit
from app.modules.github.models import Repository, user_repository

POLICY_VERSION = "2.0"
ACCESS = "repository_access"
EXTERNAL = "external_ai"
# Add providers only after privacy/legal review and configuration of a real client.
ALLOWED_PROVIDERS = frozenset({"openai"})
BLOCKED_PARTS = frozenset({".env", ".git", "node_modules", "__pycache__"})


def validate_paths(paths: list[str]) -> list[str]:
    if not paths or len(paths) > 100 or len(set(paths)) != len(paths):
        raise HTTPException(422, "Invalid scope")
    for path in paths:
        parts = path.split("/")
        if (
            not path
            or len(path) > 512
            or path.startswith("/")
            or "\\" in path
            or any(p in ("", ".", "..") for p in parts)
            or any(p in BLOCKED_PARTS or p.startswith(".env") for p in parts)
            or any(c in path for c in ("*", "?", "\x00"))
            or str(PurePosixPath(path)) != path
        ):
            raise HTTPException(422, "Invalid scope")
    return paths


def owned_repo(db: Session, user_id: int, repo_id: int) -> Repository:
    repo = db.scalar(
        select(Repository)
        .join(user_repository, Repository.id == user_repository.c.repository_id)
        .where(Repository.id == repo_id, user_repository.c.user_id == user_id)
    )
    if repo is None:
        raise HTTPException(404, "Repository not found")
    return repo


def normalize_type(kind: str, provider: str) -> str:
    if kind not in (ACCESS, EXTERNAL):
        raise HTTPException(422, "Invalid consent type")
    if kind == ACCESS:
        if provider:
            raise HTTPException(422, "Provider must be empty for repository access")
        return ""
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(422, "Unsupported provider")
    return provider


def consent_stmt(user_id: int, repo_id: int, kind: str, provider: str):
    return select(PrivateConsent).where(
        PrivateConsent.user_id == user_id,
        PrivateConsent.repository_id == repo_id,
        PrivateConsent.consent_type == kind,
        PrivateConsent.provider_key == provider,
    )


def grant(
    db: Session,
    user_id: int,
    repo_id: int,
    kind: str,
    provider: str,
    paths: list[str],
    version: str,
) -> PrivateConsent:
    provider = normalize_type(kind, provider)
    validate_paths(paths)
    if version != POLICY_VERSION:
        raise HTTPException(409, "Consent policy version changed")
    repo = owned_repo(db, user_id, repo_id)
    if not repo.private:
        raise HTTPException(409, "Repository is not private")
    # Serialize grants and revocations for this repository via a row lock.
    db.scalar(select(Repository).where(Repository.id == repo_id).with_for_update())
    record = db.scalar(consent_stmt(user_id, repo_id, kind, provider))
    if record is None:
        record = PrivateConsent(
            user_id=user_id,
            repository_id=repo_id,
            consent_type=kind,
            provider_key=provider,
        )
        db.add(record)
    record.granted = True
    record.policy_version = version
    record.scope = list(paths)
    record.granted_at = datetime.now(UTC)
    record.revoked_at = None
    db.add(
        PrivateConsentAudit(
            user_id=user_id,
            repository_id=repo_id,
            consent_type=kind,
            provider_key=provider,
            action="granted",
            policy_version=version,
            scope=list(paths),
        )
    )
    db.commit()
    db.refresh(record)
    return record


def revoke(db: Session, user_id: int, repo_id: int, kind: str, provider: str) -> None:
    provider = normalize_type(kind, provider)
    owned_repo(db, user_id, repo_id)
    jobs = []
    if kind == ACCESS:
        # Match the worker's lock order: jobs first, then the repository.
        jobs = db.scalars(
            select(AnalysisJob)
            .where(
                AnalysisJob.user_id == user_id,
                AnalysisJob.repo_id == repo_id,
                AnalysisJob.status.in_(ACTIVE),
            )
            .order_by(AnalysisJob.id)
            .with_for_update()
        ).all()
    db.scalar(select(Repository).where(Repository.id == repo_id).with_for_update())
    record = db.scalar(consent_stmt(user_id, repo_id, kind, provider))
    if record is None:
        raise HTTPException(404, "Consent not found")
    record.granted = False
    record.revoked_at = datetime.now(UTC)
    db.add(
        PrivateConsentAudit(
            user_id=user_id,
            repository_id=repo_id,
            consent_type=kind,
            provider_key=provider,
            action="revoked",
            policy_version=record.policy_version,
            scope=list(record.scope),
        )
    )
    for job in jobs:
        job.status = "cancel_requested"
        request_cleanup(db, job, reason="consent_revoked")
    db.commit()


def require_double_consent(
    db: Session, user_id: int, repo_id: int, provider: str, paths: list[str]
) -> None:
    """Call at the actual AI egress boundary, not just at job creation."""
    validate_paths(paths)
    normalize_type(EXTERNAL, provider)
    repo = owned_repo(db, user_id, repo_id)
    if not repo.private:
        return
    access = db.scalar(consent_stmt(user_id, repo_id, ACCESS, ""))
    external = db.scalar(consent_stmt(user_id, repo_id, EXTERNAL, provider))
    if (
        not access
        or not external
        or any(
            not c.granted
            or c.policy_version != POLICY_VERSION
            or c.revoked_at is not None
            for c in (access, external)
        )
    ):
        raise HTTPException(403, "Double consent required")
    if not set(paths).issubset(set(access.scope) & set(external.scope)):
        raise HTTPException(403, "Scope not approved")
