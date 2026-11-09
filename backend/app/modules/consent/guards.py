"""Fail-closed checks for private repository analysis."""

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.consent.models import PrivateConsent
from app.modules.consent.service import ACCESS, POLICY_VERSION
from app.modules.github.models import Repository


def require_private_access_consent(db, user_id: int, repo_id: int) -> None:
    repo = db.scalar(select(Repository).where(Repository.id == repo_id))
    if repo is None:
        raise HTTPException(404, "Repository not found")
    if not repo.private:
        return
    record = db.scalar(
        select(PrivateConsent).where(
            PrivateConsent.user_id == user_id,
            PrivateConsent.repository_id == repo_id,
            PrivateConsent.consent_type == ACCESS,
            PrivateConsent.provider_key == "",
        )
    )
    if (
        record is None
        or not record.granted
        or record.revoked_at is not None
        or record.policy_version != POLICY_VERSION
    ):
        raise HTTPException(403, "Private repository consent required")
