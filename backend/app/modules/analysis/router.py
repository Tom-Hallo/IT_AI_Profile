"""API routes for repository code, language, framework & architecture analysis and
background jobs (PBI-011 & PBI-012).
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.modules.analysis import service
from app.modules.analysis.models import AnalysisJobEvent
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
from app.workers.enqueue import enqueue_task

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# PBI-011: Background Analysis Jobs Router
# -----------------------------------------------------------------------------

jobs_router = APIRouter(prefix="/analysis/jobs", tags=["Analysis Jobs"])


class CreateRequest(BaseModel):
    repo_id: int = Field(gt=0)
    scope: str = Field(pattern=r"^(full|activity|skills)$")


def csrf(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin.rstrip("/") != settings.frontend_url.rstrip("/"):
        raise HTTPException(status_code=403, detail="Invalid Origin")


def dispatch(job: Any, db: Session) -> None:
    """Fail closed if Redis cannot accept the job; do not leave it queued."""
    try:
        enqueue_task("app.workers.tasks.analysis.run_analysis", str(job.id))
    except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
        logger.error("Analysis enqueue failed: %s", type(exc).__name__)
        service.fail_dispatch(db, job.id)
        raise HTTPException(
            status_code=503,
            detail="Analysis queue unavailable. Please retry later.",
        ) from exc


@jobs_router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_job(
    body: CreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
):
    csrf(request)
    job, created = service.create(db, user.id, body.repo_id, body.scope)
    if created:
        dispatch(job, db)
    return service.serialize(job)


@jobs_router.get("/{job_id}")
def get_job(
    job_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
):
    return service.serialize(service.owned_job(db, user.id, job_id))


@jobs_router.get("/{job_id}/events")
def get_events(
    job_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
):
    service.owned_job(db, user.id, job_id)
    rows = db.scalars(
        select(AnalysisJobEvent)
        .where(AnalysisJobEvent.job_id == job_id)
        .order_by(AnalysisJobEvent.id)
        .limit(500)
    ).all()
    return [
        {
            "status": item.status,
            "progress": item.progress,
            "step": item.step,
            "code": item.code,
            "created_at": item.created_at,
        }
        for item in rows
    ]


@jobs_router.post("/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_job(
    job_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
):
    csrf(request)
    return service.serialize(service.cancel(db, user.id, job_id))


@jobs_router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_job(
    job_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
):
    csrf(request)
    job, created = service.retry(db, user.id, job_id)
    if created:
        dispatch(job, db)
    return service.serialize(job)


# -----------------------------------------------------------------------------
# PBI-012: Repository Static Analysis & Evidence Router
# -----------------------------------------------------------------------------

repo_router = APIRouter(prefix="/repositories", tags=["Repository Analysis"])


@repo_router.post(
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
    """Kích hoạt tiến trình phân tích tĩnh mã nguồn, ngôn ngữ, framework và kiến trúc
    repository.
    """
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


@repo_router.get(
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


@repo_router.get(
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
    """Truy xuất danh sách bằng chứng xác thực gắn với file path và commit SHA
    (PBI-012/PBI-015).
    """
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


# -----------------------------------------------------------------------------
# Combined Router Export
# -----------------------------------------------------------------------------

router = APIRouter()
router.include_router(jobs_router)
router.include_router(repo_router)
