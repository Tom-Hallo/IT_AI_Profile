"""FastAPI Router cho Resume Pattern Analysis & Generation (PBI-032)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_current_user
from app.modules.cvs.engine import ResumePatternEngine
from app.modules.cvs.schemas import (
    PatternExtractRequest,
    PatternExtractResponse,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
    ResumePatternSuggestion,
    TargetRole,
)
from app.modules.users.models import User

router = APIRouter(prefix="/resume", tags=["Resume Intelligence"])


def get_resume_engine() -> ResumePatternEngine:
    return ResumePatternEngine()


@router.get(
    "/patterns/{role}",
    response_model=ResumePatternSuggestion,
    summary="Lấy gợi ý pattern bố cục chuẩn theo vị trí tuyển dụng",
)
def get_role_pattern(
    role: TargetRole,
    engine: Annotated[ResumePatternEngine, Depends(get_resume_engine)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> ResumePatternSuggestion:
    response.headers["Cache-Control"] = "no-store"
    return engine.get_pattern_suggestion(role)


@router.post(
    "/patterns/extract",
    response_model=PatternExtractResponse,
    summary="Trích xuất bố cục cấu trúc từ CV tham khảo",
)
def extract_pattern(
    req: PatternExtractRequest,
    engine: Annotated[ResumePatternEngine, Depends(get_resume_engine)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> PatternExtractResponse:
    response.headers["Cache-Control"] = "no-store"
    if not req.has_usage_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn cần xác nhận quyền sử dụng hợp pháp tài liệu tham khảo.",
        )
    sections = engine.extract_layout_from_reference(req.reference_text)
    return PatternExtractResponse(
        sections_detected=sections,
        formatting_insights=[
            f"Phát hiện {len(sections)} phân đoạn chính.",
            "Cấu trúc tập trung vào kết quả định lượng và kỹ năng công nghệ.",
        ],
    )


@router.post(
    "/generate",
    response_model=ResumeGenerateResponse,
    summary="Tạo CV gốc từ dữ kiện đã xác nhận của người dùng và chống đạo văn",
)
def generate_resume(
    req: ResumeGenerateRequest,
    engine: Annotated[ResumePatternEngine, Depends(get_resume_engine)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> ResumeGenerateResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return engine.generate_original_resume(req)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
