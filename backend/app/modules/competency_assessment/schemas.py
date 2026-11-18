"""Response schemas for PBI-034 Multi-source Extended Competency Assessment.

Verified Assessment: only evidence that passed contribution verification (GitHub).
Extended Assessment: verified + self-reported claims (+ future CV-derived claims).
Self-reported / claims MUST NOT alter the Verified Score.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.scoring.schemas import Limitation
from app.modules.role_scoring.schemas import (
    CriterionOut,
    EvidenceRefOut,
    RoleScoreResponse,
)


class SourceSummary(BaseModel):
    """Nguồn bằng chứng được dùng trong một assessment layer."""

    source: Literal["github", "self_reported", "cv"]
    evidence_count: int = 0
    confidence_note: str


class ConflictItem(BaseModel):
    """Mâu thuẫn giữa các nguồn (ví dụ self-reported cao nhưng verified thấp)."""

    skill_or_criterion: str
    verified_value: str | None = None
    claim_value: str | None = None
    claim_source: Literal["self_reported", "cv"]
    explanation: str


class MissingItem(BaseModel):
    """Tiêu chí / kỹ năng còn thiếu bằng chứng."""

    key: str
    description: str
    required: bool = False
    suggestion: str | None = None


class ClaimEvidenceOut(BaseModel):
    """Một minh chứng tự khai báo (self-reported) hoặc từ CV."""

    id: int | None = None
    title: str
    description: str | None = None
    url: str | None = None
    source: Literal["self_reported", "cv"] = "self_reported"
    confidence: float = Field(ge=0.0, le=1.0, description="0..1, claims always low")
    created_at: datetime | None = None


class ClaimedSkillOut(BaseModel):
    """Kỹ năng tự khai báo kèm minh chứng và độ tin cậy thấp."""

    id: int
    skill_name: str
    description: str | None = None
    source: Literal["self_reported", "cv"] = "self_reported"
    status: str = "self-reported"
    confidence: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Claims have structurally lower confidence than verified evidence",
    )
    evidence: list[ClaimEvidenceOut] = Field(default_factory=list)
    limitation: str = (
        "Self-reported skill is not independently verified by the system. "
        "It does not contribute to Verified Assessment score."
    )


class AssessmentLayerOut(BaseModel):
    """Một lớp đánh giá (Verified hoặc Extended)."""

    layer: Literal["verified", "extended"]
    status: str
    score: float | None = None
    confidence: float | None = None
    coverage: float | None = None
    rationale: str | None = None
    sources: list[SourceSummary] = Field(default_factory=list)
    criteria: list[CriterionOut] = Field(default_factory=list)
    claimed_skills: list[ClaimedSkillOut] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    evidence_refs: list[EvidenceRefOut] = Field(default_factory=list)


class CompetencyAssessmentResponse(BaseModel):
    """Phản hồi chính của PBI-034.

    ``verified`` và ``extended`` luôn tách biệt.
    Claim / self-reported không bao giờ làm thay đổi ``verified.score``.
    """

    role_key: str
    role_name: str
    rubric_version: str
    verified: AssessmentLayerOut
    extended: AssessmentLayerOut
    conflicts: list[ConflictItem] = Field(default_factory=list)
    missing: list[MissingItem] = Field(default_factory=list)
    generated_at: datetime
    verified_detail: RoleScoreResponse | None = None
