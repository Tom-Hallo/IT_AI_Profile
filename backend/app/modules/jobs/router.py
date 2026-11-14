"""FastAPI Router cho phân tích JD (PBI-025) và tìm việc Internet (PBI-026)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_current_user
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
from app.modules.users.models import User

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def get_jd_service() -> JDAnalysisService:
    return JDAnalysisService()


def get_job_search_service() -> JobSearchService:
    return JobSearchService()


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


@router.post(
    "/search",
    response_model=JobSearchResponse,
    summary="Tìm việc trên Internet theo yêu cầu người dùng (PBI-026)",
    description=(
        "Chỉ chạy khi người dùng chủ động gửi request (opt-in). "
        "Lấy tin từ nguồn/API được phép (Remotive). "
        "Trả title, company, source, link gốc, thời điểm lấy tin. "
        "Khử trùng lặp và báo rõ trạng thái nguồn (ok / empty / timeout / error)."
    ),
)
def search_jobs(
    req: JobSearchRequest,
    service: Annotated[JobSearchService, Depends(get_job_search_service)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> JobSearchResponse:
    """Endpoint opt-in tìm việc từ Internet."""
    response.headers["Cache-Control"] = "no-store"
    _ = user
    return service.search(req)
