"""API routes for repository code, language, framework & architecture analysis (PBI-012)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.analysis.schemas import (
    EvidenceListResponse,
    RepositoryAnalysisRequest,
    RepositoryAnalysisResponse,
)
from app.modules.analysis.service import (
    analyze_repository,
    get_analysis_evidence,
    get_latest_analysis,
)
from app.modules.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repositories", tags=["Repository Analysis"])


@router.post(
    "/{repository_id}/analyze",
    response_model=RepositoryAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger repository static code, framework & architecture analysis",
)
async def trigger_repository_analysis(
    repository_id: int,
    request: RepositoryAnalysisRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> RepositoryAnalysisResponse:
    """Kích hoạt tiến trình phân tích tĩnh mã nguồn, ngôn ngữ, framework và kiến trúc repository."""
    result = await analyze_repository(
        db=db,
        repository_id=repository_id,
        user=current_user,
        request=request,
    )
    return RepositoryAnalysisResponse(
        repository_id=result["repository_id"],
        commit_sha=result["commit_sha"],
        analyzed_at=result["analyzed_at"],
        scope=result["scope"],
        time_range=result.get("time_range"),
        structure=result["structure"],
        languages=result["languages"],
        frameworks=result["frameworks"],
        architecture=result["architecture"],
        evidence_count=len(result.get("evidence", [])),
        budget=result["budget"],
    )


@router.get(
    "/{repository_id}/analysis",
    response_model=RepositoryAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Get latest repository analysis report",
)
def get_repository_analysis_report(
    repository_id: int,
    commit_sha: str | None = Query(
        default=None, description="Lọc theo commit hash cụ thể"
    ),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> RepositoryAnalysisResponse:
    """Lấy kết quả phân tích gần nhất của repository đã được thực hiện."""
    result = get_latest_analysis(
        db=db,
        repository_id=repository_id,
        user=current_user,
        commit_sha=commit_sha,
    )
    return RepositoryAnalysisResponse(
        repository_id=result["repository_id"],
        commit_sha=result["commit_sha"],
        analyzed_at=result["analyzed_at"],
        scope=result["scope"],
        time_range=result.get("time_range"),
        structure=result["structure"],
        languages=result["languages"],
        frameworks=result["frameworks"],
        architecture=result["architecture"],
        evidence_count=len(result.get("evidence", [])),
        budget=result["budget"],
    )


@router.get(
    "/{repository_id}/analysis/evidence",
    response_model=EvidenceListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get verifiable evidence records for repository analysis",
)
def get_repository_evidence_records(
    repository_id: int,
    commit_sha: str | None = Query(
        default=None, description="Lọc bằng chứng theo commit SHA"
    ),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> EvidenceListResponse:
    """Truy xuất danh sách bằng chứng xác thực gắn với file path và commit SHA (PBI-012/PBI-015)."""
    evidence_items = get_analysis_evidence(
        db=db,
        repository_id=repository_id,
        user=current_user,
        commit_sha=commit_sha,
    )
    actual_sha = commit_sha or (evidence_items[0].commit_sha if evidence_items else "")
    return EvidenceListResponse(
        repository_id=repository_id,
        commit_sha=actual_sha,
        total=len(evidence_items),
        items=evidence_items,
    )
