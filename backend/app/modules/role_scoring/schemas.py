"""Response schema công khai của API Role Scoring (PBI-017 / PBI-018).

Whitelist tường minh: KHÔNG đưa ``matched_content``, ``line_number`` hay ``rationale``
của evidence (kể cả evidence do PBI-016 cung cấp) ra API. Chỉ trả tham chiếu truy xuất
(repository, commit, file_path, loại, confidence) cho chính chủ.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.ai.scoring import EvidenceRef, RoleRubric, RoleScoreResult
from app.ai.scoring.schemas import Limitation
from app.modules.role_scoring.service import RoleScoringOutcome


class EvidenceRefOut(BaseModel):
    evidence_id: str | None = None
    repository_id: int | None = None
    commit_sha: str | None = None
    file_path: str | None = None
    finding_type: str | None = None
    classification: str | None = None
    confidence_score: float
    verified: bool

    @classmethod
    def from_ref(cls, ref: EvidenceRef) -> EvidenceRefOut:
        return cls(
            evidence_id=ref.evidence_id,
            repository_id=ref.repository_id,
            commit_sha=ref.commit_sha,
            file_path=ref.file_path,
            finding_type=ref.finding_type,
            classification=ref.classification,
            confidence_score=ref.confidence_score,
            verified=ref.verified,
        )


class EvidenceExclusionOut(BaseModel):
    evidence_key: str
    reason: str


class CriterionOut(BaseModel):
    key: str
    name: str
    description: str
    type: str
    weight: float
    required: bool
    status: str
    score: float | None
    confidence: float | None
    reason_code: str
    rationale: str
    skill_key_used: str | None = None
    matched_patterns: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRefOut] = Field(default_factory=list)
    excluded_evidence: list[EvidenceExclusionOut] = Field(default_factory=list)


class SkillInputOut(BaseModel):
    status: str
    snapshot_ref: str | None = None
    snapshot_status: str | None = None
    issues: list[Limitation] = Field(default_factory=list)


class RepositoryInputOut(BaseModel):
    repository_id: int
    status: str
    report_id: int | None = None
    commit_sha: str | None = None
    evidence_used: int = 0
    excluded_by_source: dict[str, int] = Field(default_factory=dict)
    contribution_verified: bool = False


class ArchitectureInputOut(BaseModel):
    status: str
    report_ref: str | None = None
    repositories: list[RepositoryInputOut] = Field(default_factory=list)


class InputsOut(BaseModel):
    skill_snapshot: SkillInputOut
    architecture: ArchitectureInputOut


class RoleScoreResponse(BaseModel):
    role_key: str
    role_name: str
    rubric_version: str
    calibration_status: str
    calibration_note: str
    status: str
    role_score: float | None
    coverage: float
    confidence: float | None
    confidence_band: str
    reason_code: str
    rationale: str
    required_unmet: list[str]
    criteria: list[CriterionOut]
    evidence_refs: list[EvidenceRefOut]
    limitations: list[Limitation]
    inputs: InputsOut
    scored_at: datetime

    @classmethod
    def from_outcome(cls, outcome: RoleScoringOutcome) -> RoleScoreResponse:
        result: RoleScoreResult = outcome.result
        rubric = outcome.rubric
        descriptions = {c.key: c.description for c in rubric.criteria}
        arch = outcome.architecture
        snapshot = outcome.skill.snapshot
        return cls(
            role_key=result.role_key,
            role_name=rubric.name,
            rubric_version=result.rubric_version,
            calibration_status=rubric.calibration_status,
            calibration_note=rubric.calibration_note,
            status=result.status.value,
            role_score=result.role_score,
            coverage=result.coverage,
            confidence=result.confidence,
            confidence_band=result.confidence_band.value,
            reason_code=result.reason_code,
            rationale=result.rationale,
            required_unmet=list(result.required_unmet),
            criteria=[
                CriterionOut(
                    key=c.key,
                    name=c.name,
                    description=descriptions.get(c.key, ""),
                    type=c.type.value,
                    weight=c.weight,
                    required=c.required,
                    status=c.status.value,
                    score=c.score,
                    confidence=c.confidence,
                    reason_code=c.reason_code,
                    rationale=c.rationale,
                    skill_key_used=c.skill_key_used,
                    matched_patterns=list(c.matched_patterns),
                    evidence_refs=[EvidenceRefOut.from_ref(r) for r in c.evidence_refs],
                    excluded_evidence=[
                        EvidenceExclusionOut(
                            evidence_key=e.evidence_key, reason=e.reason
                        )
                        for e in c.excluded_evidence
                    ],
                )
                for c in result.criteria
            ],
            evidence_refs=[EvidenceRefOut.from_ref(r) for r in result.evidence_refs],
            limitations=list(result.limitations),
            inputs=InputsOut(
                skill_snapshot=SkillInputOut(
                    status=outcome.skill.status.value,
                    snapshot_ref=snapshot.snapshot_ref if snapshot else None,
                    snapshot_status=snapshot.status.value if snapshot else None,
                    issues=list(outcome.skill.issues),
                ),
                architecture=ArchitectureInputOut(
                    status=arch.status.value,
                    report_ref=arch.evidence_set.report_ref
                    if arch.evidence_set
                    else None,
                    repositories=[
                        RepositoryInputOut(
                            repository_id=r.repository_id,
                            status=r.status.value,
                            report_id=r.report_id,
                            commit_sha=r.commit_sha,
                            evidence_used=r.evidence_used,
                            excluded_by_source=dict(r.excluded_by_source),
                            contribution_verified=r.contribution_verified,
                        )
                        for r in arch.repositories
                    ],
                ),
            ),
            scored_at=result.scored_at,
        )


class CriterionSummary(BaseModel):
    key: str
    name: str
    description: str
    type: str
    weight: float
    required: bool


class RoleSummary(BaseModel):
    role_key: str
    name: str
    description: str
    rubric_version: str
    calibration_status: str
    calibration_note: str
    min_coverage: float
    criteria: list[CriterionSummary]

    @classmethod
    def from_rubric(cls, rubric: RoleRubric) -> RoleSummary:
        return cls(
            role_key=rubric.role_key,
            name=rubric.name,
            description=rubric.description,
            rubric_version=rubric.rubric_version,
            calibration_status=rubric.calibration_status,
            calibration_note=rubric.calibration_note,
            min_coverage=rubric.thresholds.min_coverage,
            criteria=[
                CriterionSummary(
                    key=c.key,
                    name=c.name,
                    description=c.description,
                    type=c.type.value,
                    weight=c.weight,
                    required=c.required,
                )
                for c in rubric.criteria
            ],
        )


class RoleListResponse(BaseModel):
    roles: list[RoleSummary]


# ---------------------------------------------------------------------------- PBI-018


class DedupSummaryOut(BaseModel):
    total_public_refs: int
    total_private_refs: int
    deduped_combined_refs: int
    duplicates_removed: int


class ScopeScoreOut(BaseModel):
    """Kết quả của một scope đơn (public / private / combined).

    ``available=False``: scope này không có repo nào (ví dụ user không có
    private repo); ``score`` sẽ là ``None`` và ``limitations`` giải thích lý do.
    """

    scope: str
    available: bool
    score: RoleScoreResponse | None = None
    limitations: list[Limitation] = Field(default_factory=list)


class ScopedRoleScoreResponse(BaseModel):
    """Phản hồi điểm role cho cả 3 scope: Public / Private / Combined.

    ``combined`` luôn được tính bằng engine riêng với evidence đã dedup —
    KHÔNG phải trung bình hay tổng của public + private.
    """

    role_key: str
    role_name: str
    rubric_version: str
    public: ScopeScoreOut
    private: ScopeScoreOut
    combined: ScopeScoreOut
    dedup_summary: DedupSummaryOut

    @classmethod
    def from_scoped_outcome(
        cls,
        outcome: ScopedScoringOutcome,  # noqa: F821 — imported lazily below
    ) -> ScopedRoleScoreResponse:
        from app.modules.role_scoring.scoped_service import ScopedScoringOutcome

        assert isinstance(outcome, ScopedScoringOutcome)
        rubric = outcome.rubric

        def _scope_out(scope_result: ScopeResult) -> ScopeScoreOut:  # noqa: F821
            from app.modules.role_scoring.scoped_service import ScopeResult

            assert isinstance(scope_result, ScopeResult)
            if not scope_result.available or scope_result.outcome is None:
                return ScopeScoreOut(
                    scope=scope_result.scope,
                    available=False,
                    score=None,
                    limitations=list(scope_result.limitations),
                )
            return ScopeScoreOut(
                scope=scope_result.scope,
                available=True,
                score=RoleScoreResponse.from_outcome(scope_result.outcome),
                limitations=list(scope_result.limitations),
            )

        ds = outcome.dedup_summary
        return cls(
            role_key=rubric.role_key,
            role_name=rubric.name,
            rubric_version=rubric.rubric_version,
            public=_scope_out(outcome.public),
            private=_scope_out(outcome.private),
            combined=_scope_out(outcome.combined),
            dedup_summary=DedupSummaryOut(
                total_public_refs=ds.total_public_refs,
                total_private_refs=ds.total_private_refs,
                deduped_combined_refs=ds.deduped_combined_refs,
                duplicates_removed=ds.duplicates_removed,
            ),
        )
