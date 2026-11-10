"""API router for repository fork, ownership and contribution verification (PBI-013)."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.analysis.models import (
    RepositoryVerification,
    VerificationEvidence,
)
from app.modules.analysis.schemas import (
    RepositoryVerificationResponse,
    VerificationEvidenceItem,
    VerificationEvidenceListResponse,
    VerificationRequest,
)
from app.modules.analysis.verification_service import (
    get_stored_verification,
    verify_repository_access,
    verify_repository_contributions,
)
from app.modules.users.models import User

logger = logging.getLogger(__name__)

verification_router = APIRouter(
    prefix="/repositories", tags=["Repository Verification"]
)


@verification_router.post(
    "/{repository_id}/verification",
    response_model=RepositoryVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger fork, ownership and contribution verification",
)
async def trigger_verification(
    repository_id: int,
    request: VerificationRequest | None = None,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> RepositoryVerificationResponse:
    """Xác minh fork, ownership và đóng góp thực tế từ GitHub API và lưu kết quả."""
    if request is None:
        request = VerificationRequest()

    return await verify_repository_contributions(
        db=db,
        repository_id=repository_id,
        user=current_user,
        request=request,
    )


@verification_router.get(
    "/{repository_id}/verification",
    response_model=RepositoryVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get latest repository verification result",
)
async def get_verification(
    repository_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> RepositoryVerificationResponse:
    """Lấy kết quả xác minh fork, ownership và đóng góp gần nhất của repository."""
    result = get_stored_verification(
        db=db,
        repository_id=repository_id,
        user=current_user,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chưa có kết quả xác minh cho repository này.",
        )

    return result


@verification_router.get(
    "/{repository_id}/verification/evidence",
    response_model=VerificationEvidenceListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get filtered verification evidence records",
)
def get_verification_evidence(
    repository_id: int,
    verification_status: Literal["all", "verified", "unverified", "unknown"] = Query(
        default="all",
        description="Lọc theo trạng thái: verified, unverified, unknown hoặc all",
    ),
    evidence_type: Literal[
        "all", "commit", "pull_request", "provenance", "ownership"
    ] = Query(
        default="all",
        description="Lọc theo loại: commit, PR, provenance, ownership hoặc all",
    ),
    page: int = Query(default=1, ge=1, description="Số trang (bắt đầu từ 1)"),
    per_page: int = Query(default=50, ge=1, le=200, description="Số bản ghi mỗi trang"),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> VerificationEvidenceListResponse:
    """Truy xuất bằng chứng xác minh commit/PR/provenance có phân trang và lọc."""
    verify_repository_access(db, repository_id, current_user)

    verif = db.scalar(
        select(RepositoryVerification)
        .where(
            RepositoryVerification.repository_id == repository_id,
            RepositoryVerification.user_id == current_user.id,
        )
        .order_by(desc(RepositoryVerification.verified_at))
    )
    if not verif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository chưa được xác minh. Vui lòng chạy xác minh trước.",
        )

    stmt = select(VerificationEvidence).where(
        VerificationEvidence.verification_id == verif.id
    )

    if verification_status != "all":
        stmt = stmt.where(
            VerificationEvidence.verification_status == verification_status
        )

    if evidence_type != "all":
        stmt = stmt.where(VerificationEvidence.evidence_type == evidence_type)

    stmt = stmt.order_by(VerificationEvidence.id.asc())

    all_items = db.scalars(stmt).all()
    total = len(all_items)

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paged_rows = all_items[start_idx:end_idx]

    items = [
        VerificationEvidenceItem(
            id=e.id,
            evidence_type=e.evidence_type,
            target_identifier=e.target_identifier,
            verification_status=e.verification_status,  # type: ignore[arg-type]
            actor_login=e.actor_login,
            actor_id=e.actor_id,
            actor_type=e.actor_type,
            html_url=e.html_url,
            title_or_message=e.title_or_message,
            is_merge=e.is_merge,
            is_bot=e.is_bot,
            is_fork_inherited=e.is_fork_inherited,
            additions=e.additions,
            deletions=e.deletions,
            pr_state=e.pr_state,
            pr_merged=e.pr_merged,
            source_repo=e.source_repo,
            target_repo=e.target_repo,
            recorded_at=(
                e.recorded_at.isoformat()
                if hasattr(e.recorded_at, "isoformat")
                else (str(e.recorded_at) if e.recorded_at else None)
            ),
            rationale=e.rationale,
            metadata=e.metadata_ if isinstance(e.metadata_, dict) else None,
        )
        for e in paged_rows
    ]

    return VerificationEvidenceListResponse(
        repository_id=repository_id,
        total=total,
        page=page,
        per_page=per_page,
        items=items,
    )
