"""FastAPI Router cho tìm việc trên Internet (PBI-026)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import get_current_user
from app.modules.jobs.schemas import JobSearchRequest, JobSearchResponse
from app.modules.jobs.search_service import JobSearchService
from app.modules.users.models import User

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def get_job_search_service() -> JobSearchService:
    return JobSearchService()


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
    # user được inject để đảm bảo đã đăng nhập (consent/auth gate)
    _ = user
    return service.search(req)