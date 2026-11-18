"""FastAPI Router cho phân tích JD và trích xuất skills (PBI-025)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_current_user
from app.modules.jobs.schemas import (
    JDAnalysisRequest,
    JDAnalysisResponse,
    JDPreviewUpdateRequest,
    JDPreviewUpdateResponse,
)
from app.modules.jobs.service import JDAnalysisService
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
