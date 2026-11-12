"""DTO trung gian cho Role-based Scoring (PBI-017).

Các DTO này là hợp đồng giữa scoring engine và nguồn dữ liệu. Chúng KHÔNG phụ thuộc
model/bảng của PBI-016 (chưa được xác nhận): PBI-016 chỉ cần map dữ liệu của mình sang
``SkillSnapshotInput`` rồi gọi engine. Điểm và confidence dùng thang 0..100 (khớp
``score_items`` trong SRS); ``EvidenceRef.confidence_score`` dùng thang 0..1 giống
``EvidenceRecord`` của PBI-012.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ai.scoring.evidence_catalog import normalize_key


class CriterionType(StrEnum):
    SKILL = "SKILL"
    ARCHITECTURE = "ARCHITECTURE"


class ScoreStatus(StrEnum):
    """Trạng thái chấm. ``UNKNOWN`` ≠ điểm 0: thiếu dữ liệu ≠ thiếu năng lực."""

    SCORED = "SCORED"
    UNKNOWN = "UNKNOWN"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"


class SnapshotStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ConfidenceBand(StrEnum):
    """Nhãn mô tả độ đầy đủ/nhất quán của bằng chứng — KHÔNG phải xác suất đúng."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


def _upper_enum(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


class TimeRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    from_at: datetime | None = None
    to_at: datetime | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.from_at and self.to_at and self.from_at > self.to_at:
            raise ValueError("time_range.from_at must be <= to_at")
        return self


# ----------------------------------------------------------------------------- Input


class EvidenceRef(BaseModel):
    """Tham chiếu tới một evidence đã được hệ thống phân tích tạo ra.

    Tương thích với ``EvidenceRecord`` (PBI-012) / ``AnalysisEvidence``; dùng
    ``EvidenceRef.from_record`` để chuyển đổi mà không phụ thuộc DB.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str | None = None
    repository_id: int | None = None
    commit_sha: str | None = None
    file_path: str | None = None
    finding_type: str | None = None
    classification: str | None = None
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    verified: bool = True
    rationale: str | None = None

    @field_validator("evidence_id", mode="before")
    @classmethod
    def _id_to_str(cls, value: Any) -> Any:
        return None if value is None else str(value)

    @model_validator(mode="after")
    def _has_identity(self) -> Self:
        if not self.evidence_id and not self.file_path:
            raise ValueError("EvidenceRef requires evidence_id or file_path")
        return self

    @property
    def dedup_key(self) -> str:
        """Khoá định danh để không đếm một evidence nhiều lần.

        Có ``commit_sha``: SHA là định danh theo nội dung, nên cùng (SHA, đường dẫn,
        loại, pattern) ở repository khác (ví dụ fork) là CÙNG một bằng chứng và không
        được tính thêm; ``repository_id`` không tham gia khoá. Không có SHA thì không
        chứng minh được hai vị trí giống nhau → giữ ``repository_id`` để tách biệt.
        """
        if self.file_path:
            return "|".join(
                [
                    "loc",
                    "" if self.commit_sha else str(self.repository_id or ""),
                    self.commit_sha or "",
                    self.file_path,
                    normalize_key(self.finding_type or ""),
                    normalize_key(self.classification or ""),
                ]
            )
        return f"id|{self.evidence_id}"

    @classmethod
    def from_record(cls, record: Any, *, evidence_id: Any = None) -> EvidenceRef:
        """Tạo từ ``EvidenceRecord`` hoặc ORM ``AnalysisEvidence`` (duck-typing)."""

        def _text(attr: str) -> str | None:
            value = getattr(record, attr, None)
            return None if value is None else str(getattr(value, "value", value))

        return cls(
            evidence_id=evidence_id
            if evidence_id is not None
            else getattr(record, "id", None),
            repository_id=getattr(record, "repository_id", None),
            commit_sha=_text("commit_sha"),
            file_path=_text("file_path"),
            finding_type=_text("finding_type"),
            classification=_text("classification"),
            confidence_score=getattr(record, "confidence_score", 1.0),
            rationale=_text("rationale"),
        )


class SourceContext(BaseModel):
    """Thông tin nguồn gốc dùng chung cho snapshot kỹ năng và bộ evidence kiến trúc."""

    model_config = ConfigDict(extra="forbid")

    report_ref: str | None = None
    commit_sha: str | None = None
    repository_scope: str | None = None
    repository_ids: list[str] = Field(default_factory=list)
    time_range: TimeRange | None = None
    analyzed_at: datetime | None = None


class SkillScoreItem(BaseModel):
    """Một dòng điểm kỹ năng do PBI-016 cung cấp (không tính lại ở PBI-017)."""

    model_config = ConfigDict(extra="forbid")

    skill_key: str = Field(min_length=1)
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence: float | None = Field(default=None, ge=0.0, le=100.0)
    status: ScoreStatus = ScoreStatus.SCORED
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    rationale: str | None = None

    @field_validator("skill_key")
    @classmethod
    def _norm_key(cls, value: str) -> str:
        key = normalize_key(value)
        if not key:
            raise ValueError("skill_key must not be blank")
        return key

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, value: Any) -> Any:
        return _upper_enum(value)

    @model_validator(mode="after")
    def _scored_needs_score(self) -> Self:
        if self.status == ScoreStatus.SCORED and self.score is None:
            raise ValueError("status SCORED requires a score")
        return self


class SkillSnapshotInput(SourceContext):
    snapshot_ref: str = Field(min_length=1)
    status: SnapshotStatus = SnapshotStatus.COMPLETE
    items: list[SkillScoreItem] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, value: Any) -> Any:
        return _upper_enum(value)


class ArchitectureEvidenceSet(SourceContext):
    evidence: list[EvidenceRef] = Field(default_factory=list)


class RoleScoringInput(BaseModel):
    """Đầu vào của engine. Nguồn vắng mặt (None) → tiêu chí tương ứng UNKNOWN."""

    model_config = ConfigDict(extra="forbid")

    role_key: str = Field(min_length=1)
    skill_snapshot: SkillSnapshotInput | None = None
    architecture: ArchitectureEvidenceSet | None = None

    @field_validator("role_key")
    @classmethod
    def _norm_role(cls, value: str) -> str:
        return normalize_key(value)


# ---------------------------------------------------------------------------- Output


class Limitation(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class EvidenceExclusion(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_key: str
    reason: str


class CriterionResult(BaseModel):
    key: str
    name: str
    type: CriterionType
    weight: float
    required: bool
    status: ScoreStatus
    score: float | None = None
    confidence: float | None = None
    reason_code: str
    rationale: str
    skill_key_used: str | None = None
    matched_patterns: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    excluded_evidence: list[EvidenceExclusion] = Field(default_factory=list)


class ScoreSource(BaseModel):
    skill_snapshot_ref: str | None = None
    skill_snapshot_status: SnapshotStatus | None = None
    skill_context: SourceContext | None = None
    architecture_context: SourceContext | None = None


class RoleScoreResult(BaseModel):
    role_key: str
    rubric_version: str
    status: ScoreStatus
    role_score: float | None = None
    coverage: float
    confidence: float | None = None
    confidence_band: ConfidenceBand = ConfidenceBand.NONE
    reason_code: str
    rationale: str
    required_unmet: list[str] = Field(default_factory=list)
    source: ScoreSource
    criteria: list[CriterionResult]
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    scored_at: datetime

    def criterion(self, key: str) -> CriterionResult:
        for item in self.criteria:
            if item.key == key:
                return item
        raise KeyError(key)
