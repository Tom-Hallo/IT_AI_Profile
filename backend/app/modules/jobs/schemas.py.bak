"""Pydantic schemas cho module Job Description Analysis (PBI-025).

Hỗ trợ phân tích JD từ Text hoặc URL:
- Phân loại Required vs Preferred skills
- Gắn confidence score, canonical skill key, đoạn trích ngữ cảnh
- Cho phép preview và chỉnh sửa kết quả trước khi lưu/match
- Cảnh báo và fallback rõ ràng khi URL không hợp lệ hoặc lỗi
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, HttpUrl


class SkillRequirementLevel(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"


class InputSourceType(StrEnum):
    RAW_TEXT = "raw_text"
    URL = "url"


class ExtractedSkill(BaseModel):
    """Kỹ năng được trích xuất từ JD."""

    skill_key: str = Field(
        ...,
        description="Canonical key chuẩn hoá (vd: python, fastapi, docker)",
    )
    raw_name: str = Field(
        ...,
        description="Tên kỹ năng gốc tìm thấy trong văn bản JD",
    )
    level: SkillRequirementLevel = Field(
        ...,
        description="Mức độ yêu cầu: bắt buộc hoặc ưu tiên",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy trích xuất (0.0 - 1.0)",
    )
    context_snippet: str | None = Field(
        None,
        description="Đoạn văn bản ngữ cảnh chứa kỹ năng để người dùng đối chiếu",
    )


class JDAnalysisRequest(BaseModel):
    """Request phân tích JD từ Text hoặc URL."""

    text: Annotated[
        str | None,
        Field(
            None,
            max_length=50_000,
            description="Nội dung văn bản JD thô cần phân tích",
        ),
    ] = None
    url: Annotated[
        HttpUrl | None,
        Field(
            None,
            description="URL công khai của tin tuyển dụng/JD",
        ),
    ] = None
    role_hint: Annotated[
        str | None,
        Field(
            None,
            max_length=100,
            description="Gợi ý vị trí tuyển dụng (nếu có, vd: Backend)",
        ),
    ] = None


class JDFallbackSuggestion(BaseModel):
    """Thông tin gợi ý fallback khi fetch URL thất bại."""

    fallback_mode: str = "paste_text"
    message: str
    target_url: str | None = None


class JDAnalysisResponse(BaseModel):
    """Kết quả phân tích JD trả về cho client."""

    source_type: InputSourceType
    source_ref: str | None = Field(None, description="URL nguồn hoặc 'raw_text'")
    raw_content_preview: str = Field(
        ...,
        description="Preview 300 ký tự đầu của văn bản JD",
    )
    title_detected: str | None = Field(
        None,
        description="Tiêu đề công việc được nhận diện từ JD",
    )
    required_skills: list[ExtractedSkill] = Field(default_factory=list)
    preferred_skills: list[ExtractedSkill] = Field(default_factory=list)
    total_skills_count: int
    warnings: list[str] = Field(default_factory=list)
    fallback: JDFallbackSuggestion | None = None


class JDPreviewUpdateRequest(BaseModel):
    """Request cập nhật/chỉnh sửa danh sách skills sau khi preview."""

    required_skills: list[ExtractedSkill]
    preferred_skills: list[ExtractedSkill]


class JDPreviewUpdateResponse(BaseModel):
    """Kết quả sau khi người dùng chỉnh sửa preview."""

    updated: bool = True
    required_skills: list[ExtractedSkill]
    preferred_skills: list[ExtractedSkill]
    total_skills_count: int
