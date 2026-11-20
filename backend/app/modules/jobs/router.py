"""FastAPI Router cho phân tích JD và trích xuất skills (PBI-025)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.consent.router import csrf
from app.modules.jobs.matching import JobMatchRequest, JobMatchResponse, match_job
from app.modules.jobs.schemas import (
    JDAnalysisRequest,
    JDAnalysisResponse,
    JDPreviewUpdateRequest,
    JDPreviewUpdateResponse,
    JobSearchRequest,
    JobSearchResponse,
)
from app.modules.jobs.search_service import JobSearchService
from app.modules.jobs.service import JDAnalysisService
from app.modules.role_scoring.skill_adapter import SkillSnapshotSourceError
from app.modules.users.models import User

router = APIRouter(prefix="/jobs", tags=["Job Description Analysis"])


def get_jd_service() -> JDAnalysisService:
    return JDAnalysisService()


@router.post(
    "/analyze",
    response_model=JDAnalysisResponse,
    summary="Phân tích JD từ văn bản hoặc đường dẫn URL",
    description=(
        "Trích xuất danh sách Required & Preferred skills từ văn bản hoặc URL. "
        "Bảo vệ chống SSRF và fallback sang paste text khi URL lỗi."
    ),
)
def analyze_job_description(
    req: JDAnalysisRequest,
    service: Annotated[JDAnalysisService, Depends(get_jd_service)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> JDAnalysisResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.analyze(req)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/preview/update",
    response_model=JDPreviewUpdateResponse,
    summary="Chỉnh sửa danh sách kỹ năng sau preview",
    description="Cho phép điều chỉnh danh sách skills trước khi lưu hoặc match.",
)
def update_job_skills_preview(
    req: JDPreviewUpdateRequest,
    service: Annotated[JDAnalysisService, Depends(get_jd_service)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> JDPreviewUpdateResponse:
    response.headers["Cache-Control"] = "no-store"
    return service.update_preview(req)


@router.post("/match", dependencies=[Depends(csrf)])
def match_requirements(
    req: JobMatchRequest,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> JobMatchResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return match_job(db, user, req)
    except SkillSnapshotSourceError:
        raise HTTPException(503, "Nguồn điểm kỹ năng chưa sẵn sàng.") from None


@router.post("/search", dependencies=[Depends(csrf)])
def search_jobs(
    req: JobSearchRequest,
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> JobSearchResponse:
    response.headers["Cache-Control"] = "no-store"
    return JobSearchService().search(req)
