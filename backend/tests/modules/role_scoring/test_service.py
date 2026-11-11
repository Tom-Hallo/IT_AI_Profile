"""Test Application Service (PBI-017): điều phối đúng thứ tự, giữ nguyên reference."""

from __future__ import annotations

import pytest

from app.ai.scoring import (
    ArchitectureEvidenceSet,
    EvidenceRef,
    RoleScoringEngine,
    RoleScoringInput,
    RubricNotFoundError,
    ScoreStatus,
)
from app.ai.scoring.schemas import Limitation
from app.modules.role_scoring.access import AccessDecision
from app.modules.role_scoring.architecture_provider import (
    ArchitectureEvidenceResult,
    ArchitectureStatus,
    RepositoryEvidenceInfo,
    RepositoryEvidenceStatus,
)
from app.modules.role_scoring.errors import PrivateConsentRequiredError
from app.modules.role_scoring.service import RoleScoringRequest, RoleScoringService
from app.modules.role_scoring.skill_adapter import (
    RawSkillSnapshot,
    SkillSnapshotAdapter,
    UnconfiguredSkillSnapshotSource,
)

USER = 3
SHA = "b" * 40


class AllowAll:
    def check(self, repository_id: int) -> AccessDecision:
        return AccessDecision.ALLOWED


class RecordingSource:
    def __init__(self, raw: RawSkillSnapshot | None) -> None:
        self.raw, self.calls = raw, 0

    def fetch(self, user_id, *, snapshot_ref=None):
        self.calls += 1
        return self.raw


class FakeArchitecture:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result, self.error, self.requested = result, error, []

    def get(self, repository_ids=None):
        self.requested.append(repository_ids)
        if self.error:
            raise self.error
        return self.result


def arch_result(*classifications: str, repo: int = 1) -> ArchitectureEvidenceResult:
    refs = [
        EvidenceRef(
            evidence_id=100 + i,
            repository_id=repo,
            commit_sha=SHA,
            file_path=f"p{i}",
            finding_type="architecture",
            classification=c,
            confidence_score=0.9,
        )
        for i, c in enumerate(classifications)
    ]
    return ArchitectureEvidenceResult(
        ArchitectureStatus.AVAILABLE,
        ArchitectureEvidenceSet(
            report_ref="analysis_report:5",
            commit_sha=SHA,
            repository_ids=[str(repo)],
            evidence=refs,
        ),
        [
            RepositoryEvidenceInfo(
                repo, RepositoryEvidenceStatus.USED, report_id=5, commit_sha=SHA
            )
        ],
    )


def skill_raw(repos: list[str] | None = None, items=None) -> RawSkillSnapshot:
    items = items or [
        {
            "skill_key": k,
            "score": s,
            "confidence": 80,
            "evidence_refs": [
                {"evidence_id": f"s-{k}", "repository_id": 1, "file_path": f"{k}.ts"}
            ],
        }
        for k, s in (("typescript", 90), ("react", 80), ("vite", 60))
    ]
    return RawSkillSnapshot(
        USER,
        {
            "snapshot_ref": "snap-42",
            "repository_ids": repos if repos is not None else ["1"],
            "items": items,
        },
    )


def make_service(source, architecture) -> RoleScoringService:
    return RoleScoringService(
        user_id=USER,
        engine=RoleScoringEngine(),
        skill_adapter=SkillSnapshotAdapter(source),
        architecture_provider=architecture,
        guard=AllowAll(),
    )


def test_orchestrates_both_sources_into_engine_and_keeps_references():
    source = RecordingSource(skill_raw())
    arch = FakeArchitecture(arch_result("frontend_backend_separation"))
    service = make_service(source, arch)

    out = service.score(RoleScoringRequest("Frontend_Developer", repository_ids=[1]))

    assert arch.requested == [[1]]
    assert source.calls == 1
    result = out.result
    assert result.role_key == "frontend_developer"
    assert result.status == ScoreStatus.SCORED
    assert result.source.skill_snapshot_ref == "snap-42"
    assert result.source.architecture_context.report_ref == "analysis_report:5"
    assert result.source.architecture_context.commit_sha == SHA
    skill_refs = {r.evidence_id for r in result.evidence_refs}
    assert {"s-typescript", "s-react", "100"} <= skill_refs
    assert result.criterion("frontend_backend_separation").status == ScoreStatus.SCORED


def test_scores_come_from_engine_not_recomputed_here():
    service = make_service(
        RecordingSource(skill_raw()),
        FakeArchitecture(arch_result("frontend_backend_separation")),
    )
    out = service.score(RoleScoringRequest("frontend_developer"))
    direct = RoleScoringEngine().score(
        RoleScoringInput(
            role_key="frontend_developer",
            skill_snapshot=out.skill.snapshot,
            architecture=out.architecture.evidence_set,
        ),
        rubric_version=out.rubric.rubric_version,
    )
    assert out.result.role_score == direct.role_score
    assert out.result.coverage == direct.coverage


def test_missing_skill_snapshot_yields_unknown_criteria_and_limitation():
    service = make_service(
        RecordingSource(None),
        FakeArchitecture(arch_result("frontend_backend_separation")),
    )

    out = service.score(RoleScoringRequest("frontend_developer"))

    assert out.result.status != ScoreStatus.SCORED
    assert out.result.role_score is None
    assert out.result.criterion("frontend_language").status == ScoreStatus.UNKNOWN
    assert out.result.criterion("frontend_language").score is None
    assert "SKILL_SNAPSHOT_MISSING" in {x.code for x in out.result.limitations}


def test_unconfigured_pbi016_never_invents_skill_scores():
    service = make_service(
        UnconfiguredSkillSnapshotSource(),
        FakeArchitecture(arch_result("frontend_backend_separation")),
    )

    out = service.score(RoleScoringRequest("frontend_developer"))

    assert out.result.role_score is None
    assert all(c.score is None for c in out.result.criteria if c.type.value == "SKILL")
    assert "SKILL_SNAPSHOT_SOURCE_NOT_CONFIGURED" in {
        x.code for x in out.result.limitations
    }


def test_missing_architecture_yields_unknown_architecture_criteria():
    service = make_service(
        RecordingSource(skill_raw()),
        FakeArchitecture(
            ArchitectureEvidenceResult(ArchitectureStatus.NOT_ANALYZED, None, [])
        ),
    )

    out = service.score(RoleScoringRequest("frontend_developer"))

    crit = out.result.criterion("frontend_backend_separation")
    assert crit.status == ScoreStatus.UNKNOWN and crit.score is None
    assert crit.reason_code == "ARCHITECTURE_EVIDENCE_UNAVAILABLE"
    # Skill vẫn đủ coverage (≥0.6) → vẫn tính điểm, không coi thiếu kiến trúc là 0.
    assert out.result.status == ScoreStatus.SCORED


def test_authorization_failure_stops_before_pbi016_is_called():
    source = RecordingSource(skill_raw())
    arch = FakeArchitecture(error=PrivateConsentRequiredError("1"))
    service = make_service(source, arch)

    with pytest.raises(PrivateConsentRequiredError):
        service.score(RoleScoringRequest("frontend_developer", repository_ids=[1]))

    assert source.calls == 0


def test_unknown_role_raises_before_touching_any_source():
    source = RecordingSource(skill_raw())
    arch = FakeArchitecture(arch_result())
    service = make_service(source, arch)

    with pytest.raises(RubricNotFoundError):
        service.score(RoleScoringRequest("astronaut"))

    assert source.calls == 0 and arch.requested == []


def test_unknown_rubric_version_raises():
    service = make_service(RecordingSource(None), FakeArchitecture(arch_result()))
    with pytest.raises(RubricNotFoundError):
        service.score(RoleScoringRequest("backend_developer", rubric_version="9.9.9"))


def test_repository_set_mismatch_is_reported():
    service = make_service(
        RecordingSource(skill_raw(repos=["1", "2"])),
        FakeArchitecture(arch_result("frontend_backend_separation", repo=1)),
    )

    out = service.score(RoleScoringRequest("frontend_developer"))

    assert "REPOSITORY_SET_MISMATCH" in {x.code for x in out.result.limitations}


def test_provider_and_adapter_limitations_are_merged_without_duplicates():
    arch = arch_result("frontend_backend_separation")
    arch.limitations.extend([Limitation(code="X_LIMIT", message="m")] * 2)
    service = make_service(RecordingSource(skill_raw()), FakeArchitecture(arch))

    out = service.score(RoleScoringRequest("frontend_developer"))

    assert [x.code for x in out.result.limitations].count("X_LIMIT") == 1


def test_list_rubrics_exposes_extensible_roles():
    service = make_service(RecordingSource(None), FakeArchitecture(arch_result()))
    roles = {r.role_key for r in service.list_rubrics()}
    assert {"backend_developer", "frontend_developer"} <= roles
