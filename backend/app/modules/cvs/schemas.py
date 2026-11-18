"""Schemas cho AI Resume Pattern Analysis & Anti-Plagiarism (PBI-032)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class TargetRole(StrEnum):
    BACKEND = "Backend Developer"
    FRONTEND = "Frontend Developer"
    FULLSTACK = "Fullstack Developer"
    DEVOPS = "DevOps Engineer"
    AI_ML = "AI / ML Engineer"


class LayoutSection(BaseModel):
    section_name: str
    purpose: str
    recommended_order: int
    bullet_style: str = "STAR (Situation, Task, Action, Result)"


class ResumePatternSuggestion(BaseModel):
    """Mẫu bố cục và cấu trúc được gợi ý cho vị trí."""

    target_role: TargetRole
    recommended_layout: list[LayoutSection]
    explanation: str
    key_highlights_focus: list[str]


class PatternExtractRequest(BaseModel):
    """Request phân tích bố cục từ reference CV."""

    reference_text: Annotated[str, Field(min_length=50, max_length=50_000)]
    has_usage_permission: bool = Field(
        ...,
        description="Xác nhận người dùng có quyền hợp pháp sử dụng reference",
    )


class PatternExtractResponse(BaseModel):
    """Kết quả phân tích bố cục từ reference CV."""

    sections_detected: list[str]
    formatting_insights: list[str]
    disclaimer: str = (
        "CẢNH BÁO: Mẫu chỉ được dùng để tham khảo cấu trúc và bố cục. "
        "Tuyệt đối không sao chép nội dung từ reference."
    )


class VerifiedUserFact(BaseModel):
    """Dữ kiện thật đã được xác nhận của người dùng."""

    fact_type: str = Field(..., description="skill, project, role, metric")
    content: str
    verified_evidence_ref: str | None = None


class ResumeGenerateRequest(BaseModel):
    """Request tạo CV gốc từ dữ kiện thật của người dùng."""

    target_role: TargetRole
    verified_facts: list[VerifiedUserFact] = Field(
        ..., min_length=1, description="Dữ kiện thật đã xác nhận của người dùng"
    )
    reference_template_text: str | None = Field(
        None,
        max_length=50_000,
        description="Nội dung CV tham khảo cấu trúc (nếu có)",
    )
    has_reference_permission: bool = Field(
        default=True,
        description="Quyền hợp pháp sử dụng reference",
    )


class GeneratedResumeSection(BaseModel):
    title: str
    bullets: list[str]


class ResumeGenerateResponse(BaseModel):
    """Kết quả tạo CV gốc."""

    target_role: TargetRole
    summary: str
    sections: list[GeneratedResumeSection]
    disclaimer: str = (
        "LƯU Ý: CV được tạo hoàn toàn từ các dữ kiện gốc đã xác minh của bạn. "
        "Bố cục chỉ mang tính chất tham khảo, không sao chép từ bên ngoài."
    )
    similarity_with_reference: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Tỉ lệ tương đồng với văn bản tham khảo (bắt buộc < 0.20)",
    )
    plagiarism_detected: bool = False
    source_facts_used_count: int
