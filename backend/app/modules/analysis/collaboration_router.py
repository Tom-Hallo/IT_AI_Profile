"""API router for Pull Request, Review, CI & Problem-Solving Analysis (PBI-014)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.analysis.collaboration_service import (
    analyze_repository_collaboration,
    get_collaboration_evidence_list,
    get_stored_collaboration,
)
from app.modules.analysis.schemas import (
    CollaborationAnalysisRequest,
    CollaborationAnalysisResponse,
    CollaborationEvidenceListResponse,
)
from app.modules.users.models import User

logger = logging.getLogger(__name__)

collaboration_router = APIRouter(
    prefix="/repositories", tags=["Repository Collaboration Analysis"]
)


@collaboration_router.post(
    "/{repository_id}/collaboration",
    response_model=CollaborationAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger Pull Request, Review, CI & Problem-Solving Analysis",
)
async def trigger_collaboration(
    repository_id: int,
    request: CollaborationAnalysisRequest | None = None,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CollaborationAnalysisResponse:
    """Thu thập và phân tích Pull Request, Review, CI checks và xử lý lỗi."""
    if request is None:
        request = CollaborationAnalysisRequest()

    return await analyze_repository_collaboration(
        db=db,
        repository_id=repository_id,
        user=current_user,
        request=request,
    )


@collaboration_router.get(
    "/{repository_id}/collaboration",
    response_model=CollaborationAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Get latest collaboration analysis result",
)
def get_collaboration(
    repository_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CollaborationAnalysisResponse:
    """Lấy kết quả phân tích cộng tác gần nhất đã lưu của repository."""
    result = get_stored_collaboration(
        db=db,
        repository_id=repository_id,
        user=current_user,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chưa có kết quả phân tích cộng tác cho repository này.",
        )

    return result


@collaboration_router.get(
    "/{repository_id}/collaboration/evidence",
    response_model=CollaborationEvidenceListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get filtered collaboration evidence records",
)
def get_collaboration_evidence(
    repository_id: int,
    analysis_id: int | None = Query(default=None, gt=0),
    evidence_type: str = Query(
        default="all",
        description="Lọc theo loại: pull_request, review, check_run, etc.",
    ),
    state: str = Query(
        default="all",
        description="Lọc theo trạng thái: merged, closed_unmerged, open, etc.",
    ),
    pr_number: int | None = Query(
        default=None,
        description="Lọc bằng chứng theo số hiệu Pull Request",
    ),
    page: int = Query(default=1, ge=1, description="Số thứ tự trang"),
    per_page: int = Query(default=50, ge=1, le=100, description="Số bản ghi mỗi trang"),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> CollaborationEvidenceListResponse:
    """Truy xuất danh sách bằng chứng cộng tác phân trang và lọc (PBI-014)."""
    return get_collaboration_evidence_list(
        db=db,
        repository_id=repository_id,
        user=current_user,
        evidence_type=evidence_type,
        state=state,
        pr_number=pr_number,
        page=page,
        per_page=per_page,
        analysis_id=analysis_id,
    )
