"""Pydantic schemas cho module Job Description Analysis (PBI-025)
và Job Search from Internet (PBI-026).
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


# ---------------------------------------------------------------------------
# PBI-026 | Job Search from Internet (opt-in)
# ---------------------------------------------------------------------------


class AllowedJobSource(StrEnum):
    """Whitelist các nguồn tin được phép sử dụng (không scraping trái phép)."""

    REMOTIVE = "remotive"


class JobSearchRequest(BaseModel):
    """Request tìm việc theo yêu cầu người dùng (opt-in).

    Người dùng phải chủ động gửi request này với tiêu chí tìm kiếm.
    """

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            max_length=200,
            description="Từ khóa tìm kiếm (vd: python backend, react developer)",
        ),
    ]
    location: Annotated[
        str | None,
        Field(
            None,
            max_length=100,
            description="Địa điểm mong muốn (vd: remote, vietnam, hanoi).",
        ),
    ] = "remote"
    sources: Annotated[
        list[AllowedJobSource],
        Field(
            default_factory=lambda: [AllowedJobSource.REMOTIVE],
            description="Danh sách nguồn được phép. Chỉ nhận whitelist.",
        ),
    ]
    limit: Annotated[
        int,
        Field(
            default=20,
            ge=1,
            le=50,
            description="Số lượng tin tối đa trả về sau khi khử trùng",
        ),
    ] = 20


class JobItem(BaseModel):
    """Một tin tuyển dụng trả về từ nguồn Internet."""

    id: str = Field(..., description="ID duy nhất (hash hoặc id từ nguồn)")
    title: str
    company: str
    source: AllowedJobSource
    url: str = Field(..., description="Link gốc của tin tuyển dụng")
    fetched_at: str = Field(
        ...,
        description="Thời điểm lấy tin (ISO 8601 UTC)",
    )
    location: str | None = None
    tags: list[str] = Field(default_factory=list)
    expired: bool = Field(
        False,
        description="True nếu nguồn báo tin đã hết hạn / không còn active",
    )
    description_preview: str | None = Field(
        None,
        description="Đoạn mô tả ngắn (nếu nguồn cung cấp)",
    )


class SourceStatus(BaseModel):
    """Trạng thái từng nguồn khi thực hiện tìm kiếm."""

    source: AllowedJobSource
    status: str = Field(
        ...,
        description="ok | error | timeout | empty | invalid",
    )
    message: str | None = None
    jobs_found: int = 0


class JobSearchResponse(BaseModel):
    """Kết quả tìm việc trả về cho client."""

    jobs: list[JobItem] = Field(default_factory=list)
    total: int = Field(..., description="Số tin sau khi khử trùng")
    deduplicated_count: int = Field(
        0,
        description="Số tin bị loại vì trùng",
    )
    source_status: list[SourceStatus] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    searched_at: str = Field(..., description="Thời điểm thực hiện tìm kiếm (ISO 8601)")
