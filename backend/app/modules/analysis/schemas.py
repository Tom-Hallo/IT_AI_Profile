"""Pydantic request & response schemas for repository analysis API (PBI-012)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.analysis.evidence import EvidenceRecord


class RepositoryAnalysisRequest(BaseModel):
    """Tham số yêu cầu phân tích repository tĩnh."""

    mode: Literal["preset", "month", "custom"] | None = Field(
        default=None, description="Chế độ chọn khoảng thời gian (PBI-010)"
    )
    preset: Literal["1m", "3m", "6m", "1y"] | None = Field(
        default=None, description="Khoảng thời gian mẫu"
    )
    month: str | None = Field(default=None, description="Tháng dạng YYYY-MM")
    start_date: date | None = Field(default=None, description="Ngày bắt đầu")
    end_date: date | None = Field(default=None, description="Ngày kết thúc")
    timezone: str = Field(default="UTC", description="Múi giờ IANA")
    scope: Literal["all", "public", "private"] = Field(
        default="all", description="Phạm vi phân tích repository"
    )


class LanguageSummary(BaseModel):
    name: str
    primary: bool
    bytes_count: int | None = None
    percentage: float | None = None
    file_count: int
    evidence_count: int


class FrameworkSummary(BaseModel):
    name: str
    category: str
    ecosystem: str
    version: str | None = None
    status: str
    confidence: str
    evidence_count: int


class ArchitectureSummary(BaseModel):
    pattern: str
    name: str
    description: str
    confidence: str
    evidence_count: int


class StructureSummary(BaseModel):
    total_files: int
    inspected_files: int
    ignored_files: int


class RepositoryAnalysisResponse(BaseModel):
    """Kết quả phân tích toàn diện repository."""

    repository_id: int
    commit_sha: str
    analyzed_at: str
    scope: str
    time_range: dict[str, str | None] | None = None
    structure: StructureSummary
    languages: list[LanguageSummary]
    frameworks: list[FrameworkSummary]
    architecture: list[ArchitectureSummary]
    evidence_count: int
    budget: dict[str, Any]


class EvidenceListResponse(BaseModel):
    """Danh sách các bản ghi bằng chứng có thể kiểm chứng độc lập."""

    repository_id: int
    commit_sha: str
    total: int
    items: list[EvidenceRecord]
