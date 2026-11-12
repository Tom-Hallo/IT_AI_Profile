"""Kiểm tra quyền + consent repository, tái sử dụng guard hiện có của PBI-012/007.

Không viết lại luật: gọi ``verify_repository_access`` (sở hữu + private access) và
``verify_private_repo_consent`` (consent ACCESS còn hiệu lực, đúng policy version).
Kết quả được chuyển thành ``AccessDecision`` để lớp trên quyết định fail-closed hay
bỏ qua từng repository.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.analysis.service import (
    verify_private_repo_consent,
    verify_repository_access,
)
from app.modules.users.models import User


class AccessDecision(StrEnum):
    ALLOWED = "ALLOWED"
    NOT_FOUND = "NOT_FOUND"
    PRIVATE_CONSENT_REQUIRED = "PRIVATE_CONSENT_REQUIRED"


class RepositoryAccessGuard(Protocol):
    def check(self, repository_id: int) -> AccessDecision: ...


class DbRepositoryAccessGuard:
    """Guard gắn với một người dùng đã xác thực."""

    def __init__(self, db: Session, user: User) -> None:
        self._db = db
        self._user = user

    def check(self, repository_id: int) -> AccessDecision:
        try:
            repo = verify_repository_access(self._db, repository_id, self._user)
            verify_private_repo_consent(repo, None, self._db, self._user.id)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                return AccessDecision.NOT_FOUND
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                return AccessDecision.PRIVATE_CONSENT_REQUIRED
            raise
        return AccessDecision.ALLOWED
