"""Schemas cho AI Mentor chat đa nguồn (PBI-021)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

SourceId = Annotated[int, Field(gt=0, le=2**63 - 1)]
SourceKey = Literal["github", "cv", "jd", "roadmap"]


class MentorSources(BaseModel):
    """Nguồn được user chọn cho một lượt hỏi."""

    github_repo_ids: list[SourceId] = Field(default_factory=list, max_length=10)
    include_cv: bool = False
    cv_ids: list[SourceId] = Field(default_factory=list, max_length=3)
    jd_text: str | None = Field(default=None, max_length=8000)
    roadmap_ids: list[SourceId] = Field(default_factory=list, max_length=5)

    @field_validator("github_repo_ids", "cv_ids", "roadmap_ids")
    @classmethod
    def _positive_ids(cls, value: list[int]) -> list[int]:
        return sorted(set(value))

    @field_validator("jd_text")
    @classmethod
    def _strip_jd(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class MentorChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    sources: MentorSources = Field(default_factory=MentorSources)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Câu hỏi không được để trống.")
        return text


class EvidenceRef(BaseModel):
    id: str
    source: SourceKey
    label: str
    detail: str | None = None


class MentorLimitation(BaseModel):
    code: str
    message: str


class MentorChatResponse(BaseModel):
    answer: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[MentorLimitation] = Field(default_factory=list)
    sources_used: list[SourceKey] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provider_available: bool = True


class MentorCVOption(BaseModel):
    id: int
    uploaded_at: datetime


class MentorRoadmapOption(BaseModel):
    id: int
    title: str


class MentorSourceOptions(BaseModel):
    cvs: list[MentorCVOption]
    roadmaps: list[MentorRoadmapOption]


class GroundedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class GroundedAnswer(BaseModel):
    claims: list[GroundedClaim] = Field(max_length=10)
    limitations: list[str] = Field(max_length=10)
