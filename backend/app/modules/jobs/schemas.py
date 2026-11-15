"""Pydantic schemas for Job Description Analysis (PBI-025)
and Job Search from Internet (PBI-026).
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
    """Extracted skill item from JD content."""

    skill_key: str = Field(
        ...,
        description="Canonical normalized skill key (e.g. python, fastapi, docker)",
    )
    raw_name: str = Field(
        ...,
        description="Raw skill name found in JD text",
    )
    level: SkillRequirementLevel = Field(
        ...,
        description="Requirement level: required or preferred",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score (0.0 - 1.0)",
    )
    context_snippet: str | None = Field(
        None,
        description="Contextual snippet containing the skill for user verification",
    )


class JDAnalysisRequest(BaseModel):
    """Request payload for analyzing JD from Text or URL."""

    text: Annotated[
        str | None,
        Field(
            None,
            max_length=50_000,
            description="Raw JD text content to be analyzed",
        ),
    ] = None
    url: Annotated[
        HttpUrl | None,
        Field(
            None,
            description="Public URL of the job posting or JD",
        ),
    ] = None
    role_hint: Annotated[
        str | None,
        Field(
            None,
            max_length=100,
            description="Optional target role hint (e.g. Backend Developer)",
        ),
    ] = None


class JDFallbackSuggestion(BaseModel):
    """Fallback suggestion payload when URL fetch fails."""

    fallback_mode: str = "paste_text"
    message: str
    target_url: str | None = None


class JDAnalysisResponse(BaseModel):
    """Analysis result returned to client."""

    source_type: InputSourceType
    source_ref: str | None = Field(
        None, description="Source reference URL or 'raw_text'"
    )
    raw_content_preview: str = Field(
        ...,
        description="First 300 characters preview of JD content",
    )
    title_detected: str | None = Field(
        None,
        description="Detected job title from JD text",
    )
    required_skills: list[ExtractedSkill] = Field(default_factory=list)
    preferred_skills: list[ExtractedSkill] = Field(default_factory=list)
    total_skills_count: int
    warnings: list[str] = Field(default_factory=list)
    fallback: JDFallbackSuggestion | None = None


class JDPreviewUpdateRequest(BaseModel):
    """Request payload for updating skill classification after preview."""

    required_skills: list[ExtractedSkill]
    preferred_skills: list[ExtractedSkill]


class JDPreviewUpdateResponse(BaseModel):
    """Response payload after user reviews and updates preview."""

    updated: bool = True
    required_skills: list[ExtractedSkill]
    preferred_skills: list[ExtractedSkill]
    total_skills_count: int


# ---------------------------------------------------------------------------
# PBI-026 | Job Search from Internet (opt-in)
# ---------------------------------------------------------------------------


class AllowedJobSource(StrEnum):
    """Whitelisted job sources for searching (no illegal scraping)."""

    REMOTIVE = "remotive"


class JobSearchRequest(BaseModel):
    """Opt-in search request triggered explicitly by user."""

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            max_length=200,
            description="Search query keywords (e.g. python backend)",
        ),
    ]
    location: Annotated[
        str | None,
        Field(
            None,
            max_length=100,
            description="Desired job location (e.g. remote, vietnam)",
        ),
    ] = "remote"
    sources: Annotated[
        list[AllowedJobSource],
        Field(
            default_factory=lambda: [AllowedJobSource.REMOTIVE],
            description="List of allowed whitelisted sources",
        ),
    ]
    limit: Annotated[
        int,
        Field(
            default=20,
            ge=1,
            le=50,
            description="Maximum number of jobs to return after deduplication",
        ),
    ] = 20


class JobItem(BaseModel):
    """Single job item returned from external sources."""

    id: str = Field(..., description="Unique job ID or hash")
    title: str
    company: str
    source: AllowedJobSource
    url: str = Field(..., description="Original URL of the job posting")
    fetched_at: str = Field(
        ...,
        description="Timestamp when the job was fetched in ISO 8601 UTC",
    )
    location: str | None = None
    tags: list[str] = Field(default_factory=list)
    expired: bool = Field(
        False,
        description="True if the source reports this job is no longer active",
    )
    description_preview: str | None = Field(
        None,
        description="Short description preview if provided by source",
    )


class SourceStatus(BaseModel):
    """Status of each source query."""

    source: AllowedJobSource
    status: str = Field(
        ...,
        description="Status string: ok | error | timeout | empty | invalid",
    )
    message: str | None = None
    jobs_found: int = 0


class JobSearchResponse(BaseModel):
    """Job search response returned to client."""

    jobs: list[JobItem] = Field(default_factory=list)
    total: int = Field(..., description="Total jobs after deduplication")
    deduplicated_count: int = Field(
        0,
        description="Number of duplicated jobs filtered out",
    )
    source_status: list[SourceStatus] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    searched_at: str = Field(
        ...,
        description="Search execution timestamp in ISO 8601 format",
    )
