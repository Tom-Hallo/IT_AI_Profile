"""Tests cho ScopedRoleScoringService (PBI-018).

Các test dùng mock/stub để không cần DB thật. Mục tiêu:
- Dedup logic đúng (cùng dedup_key chỉ được tính 1 lần).
- Combined KHÔNG phải trung bình hay tổng public + private.
- Scope không có repo → available=False, limitations rõ.
- Confidence / limitations được truyền qua đúng.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.ai.scoring.schemas import (
    ArchitectureEvidenceSet,
    ConfidenceBand,
    EvidenceRef,
    Limitation,
    RoleScoreResult,
    ScoreSource,
    ScoreStatus,
    SkillScoreItem,
    SkillSnapshotInput,
    SnapshotStatus,
)
from app.modules.role_scoring.architecture_provider import (
    ArchitectureEvidenceResult,
    ArchitectureStatus,
)
from app.modules.role_scoring.scoped_service import (
    DedupSummary,
    ScopedRoleScoringService,
    ScopeResult,
)
from app.modules.role_scoring.skill_adapter import (
    SkillSnapshotResult,
    SkillSnapshotStatus,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _make_evidence_ref(
    *,
    evidence_id: str | None = None,
    repository_id: int = 1,
    commit_sha: str = "abc123",
    file_path: str = "src/main.py",
    finding_type: str = "architecture",
    classification: str = "api_layer",
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        repository_id=repository_id,
        commit_sha=commit_sha,
        file_path=file_path,
        finding_type=finding_type,
        classification=classification,
        confidence_score=0.9,
        verified=True,
    )


def _make_arch_result(refs: list[EvidenceRef]) -> ArchitectureEvidenceResult:
    if not refs:
        return ArchitectureEvidenceResult(
            status=ArchitectureStatus.NOT_ANALYZED,
            evidence_set=None,
        )
    return ArchitectureEvidenceResult(
        status=ArchitectureStatus.AVAILABLE,
        evidence_set=ArchitectureEvidenceSet(
            report_ref="report:1",
            repository_ids=["1"],
            evidence=refs,
        ),
    )


def _make_skill_result(
    items: list[SkillScoreItem] | None = None,
) -> SkillSnapshotResult:
    if items is None:
        return SkillSnapshotResult(status=SkillSnapshotStatus.MISSING)
    snap = SkillSnapshotInput(
        snapshot_ref="snap_ref",
        status=SnapshotStatus.COMPLETE,
        items=items,
    )
    return SkillSnapshotResult(status=SkillSnapshotStatus.AVAILABLE, snapshot=snap)


def _make_score_result(role_key: str = "backend_developer") -> RoleScoreResult:

    return RoleScoreResult(
        role_key=role_key,
        rubric_version="1.0.0",
        status=ScoreStatus.SCORED,
        role_score=75.0,
        coverage=0.8,
        confidence=70.0,
        confidence_band=ConfidenceBand.MEDIUM,
        reason_code="SCORED",
        rationale="ok",
        source=ScoreSource(),
        criteria=[],
        scored_at=_now(),
    )


def _make_outcome(
    arch_refs: list[EvidenceRef] | None = None,
    skill_items: list[SkillScoreItem] | None = None,
) -> MagicMock:
    from app.modules.role_scoring.service import RoleScoringOutcome

    outcome = MagicMock(spec=RoleScoringOutcome)
    outcome.result = _make_score_result()
    outcome.rubric = MagicMock()
    outcome.rubric.role_key = "backend_developer"
    outcome.rubric.rubric_version = "1.0.0"
    outcome.architecture = _make_arch_result(arch_refs or [])
    outcome.skill = _make_skill_result(skill_items)
    return outcome


# ---------------------------------------------------------------- unit tests


class TestScopeResultModel:
    def test_unavailable_scope_has_no_outcome(self) -> None:
        s = ScopeResult(
            scope="public",
            available=False,
            outcome=None,
            limitations=[Limitation(code="NO_REPO", message="no repo")],
        )
        assert not s.available
        assert s.outcome is None
        assert len(s.limitations) == 1

    def test_available_scope_has_outcome(self) -> None:
        outcome = _make_outcome()
        s = ScopeResult(scope="private", available=True, outcome=outcome)
        assert s.available
        assert s.outcome is outcome


class TestDedupSummary:
    def test_zero_duplicates(self) -> None:
        ds = DedupSummary(
            total_public_refs=3,
            total_private_refs=4,
            deduped_combined_refs=7,
            duplicates_removed=0,
        )
        assert ds.duplicates_removed == 0
        assert ds.deduped_combined_refs == ds.total_public_refs + ds.total_private_refs

    def test_with_duplicates(self) -> None:
        ds = DedupSummary(
            total_public_refs=3,
            total_private_refs=3,
            deduped_combined_refs=4,
            duplicates_removed=2,
        )
        assert ds.duplicates_removed == 2


class TestMergeSkillSnapshots:
    """Unit test _merge_skill_snapshots (static method)."""

    def _item(self, key: str, score: float) -> SkillScoreItem:
        return SkillScoreItem(
            skill_key=key,
            score=score,
            confidence=score,
            status=ScoreStatus.SCORED,
            evidence_refs=[
                EvidenceRef(
                    evidence_id=f"ev_{key}_{int(score)}",
                    file_path=f"src/{key}.py",
                )
            ],
        )

    def test_public_only(self) -> None:
        pub_snap = SkillSnapshotInput(
            snapshot_ref="pub",
            status=SnapshotStatus.COMPLETE,
            items=[self._item("python", 80.0)],
        )
        result = ScopedRoleScoringService._merge_skill_snapshots(pub_snap, None)
        assert result is not None
        assert len(result.items) == 1
        assert result.items[0].skill_key == "python"

    def test_private_only(self) -> None:
        priv_snap = SkillSnapshotInput(
            snapshot_ref="priv",
            status=SnapshotStatus.COMPLETE,
            items=[self._item("typescript", 70.0)],
        )
        result = ScopedRoleScoringService._merge_skill_snapshots(None, priv_snap)
        assert result is not None
        assert len(result.items) == 1

    def test_both_none_returns_none(self) -> None:
        result = ScopedRoleScoringService._merge_skill_snapshots(None, None)
        assert result is None

    def test_dedup_keeps_first_identical_evidence(self) -> None:
        """Cùng bộ evidence: giữ một bản nhất quán."""
        pub_snap = SkillSnapshotInput(
            snapshot_ref="pub",
            status=SnapshotStatus.COMPLETE,
            items=[self._item("python", 60.0)],
        )
        priv_snap = SkillSnapshotInput(
            snapshot_ref="priv",
            status=SnapshotStatus.COMPLETE,
            items=[self._item("python", 90.0)],
        )
        result = ScopedRoleScoringService._merge_skill_snapshots(pub_snap, priv_snap)
        assert result is not None
        # Chỉ còn một item cho cùng bộ bằng chứng
        python_items = [i for i in result.items if i.skill_key == "python"]
        assert len(python_items) == 1
        assert python_items[0].score == 60.0

    def test_same_skill_keeps_distinct_evidence(self) -> None:
        public = self._item("python", 72.0)
        private = self._item("python", 78.0).model_copy(
            update={
                "evidence_refs": [
                    EvidenceRef(
                        evidence_id="unique-private", file_path="services/other.py"
                    )
                ]
            }
        )
        merged = ScopedRoleScoringService._merge_skill_snapshots(
            SkillSnapshotInput(snapshot_ref="pub", items=[public]),
            SkillSnapshotInput(snapshot_ref="priv", items=[private]),
        )
        assert merged is not None
        assert merged.items == [public, private]

    def test_different_skills_merged(self) -> None:
        pub_snap = SkillSnapshotInput(
            snapshot_ref="pub",
            status=SnapshotStatus.COMPLETE,
            items=[self._item("python", 80.0), self._item("javascript", 70.0)],
        )
        priv_snap = SkillSnapshotInput(
            snapshot_ref="priv",
            status=SnapshotStatus.COMPLETE,
            items=[self._item("rust", 65.0)],
        )
        result = ScopedRoleScoringService._merge_skill_snapshots(pub_snap, priv_snap)
        assert result is not None
        keys = {i.skill_key for i in result.items}
        assert keys == {"python", "javascript", "rust"}

    def test_combined_snapshot_ref_is_derived_from_source(self) -> None:
        pub_snap = SkillSnapshotInput(
            snapshot_ref="my_pub_ref",
            status=SnapshotStatus.COMPLETE,
            items=[self._item("python", 80.0)],
        )
        result = ScopedRoleScoringService._merge_skill_snapshots(pub_snap, None)
        assert result is not None
        assert result.snapshot_ref.startswith("combined_")


class TestEvidenceDedupLogic:
    """Kiểm tra logic dedup evidence trong _score_combined (gián tiếp qua dedup_key)."""

    def test_same_commit_same_file_deduped(self) -> None:
        """Cùng commit_sha + file_path → chỉ tính 1 lần."""
        ref = _make_evidence_ref(
            commit_sha="same_sha",
            file_path="src/api.py",
            classification="api_layer",
        )
        # Ref giống hệt nhau (public và private cùng có)
        pub_refs = [ref]
        priv_refs = [ref]  # cùng ref → cùng dedup_key

        seen: set[str] = set()
        combined: list[EvidenceRef] = []
        for r in pub_refs + priv_refs:
            k = r.dedup_key
            if k not in seen:
                seen.add(k)
                combined.append(r)

        assert len(combined) == 1  # deduped!

    def test_different_files_not_deduped(self) -> None:
        ref1 = _make_evidence_ref(
            commit_sha="sha1", file_path="src/a.py", classification="api_layer"
        )
        ref2 = _make_evidence_ref(
            commit_sha="sha1", file_path="src/b.py", classification="api_layer"
        )

        seen: set[str] = set()
        combined: list[EvidenceRef] = []
        for r in [ref1, ref2]:
            k = r.dedup_key
            if k not in seen:
                seen.add(k)
                combined.append(r)

        assert len(combined) == 2  # không dedup vì file_path khác

    def test_no_commit_sha_uses_repo_id_for_dedup(self) -> None:
        """Không có SHA → dùng repository_id; 2 repo khác nhau = 2 evidence."""
        ref1 = EvidenceRef(
            file_path="src/main.py",
            repository_id=1,
            finding_type="architecture",
            classification="api_layer",
            confidence_score=0.9,
        )
        ref2 = EvidenceRef(
            file_path="src/main.py",
            repository_id=2,  # repo khác
            finding_type="architecture",
            classification="api_layer",
            confidence_score=0.9,
        )

        assert ref1.dedup_key != ref2.dedup_key

    def test_with_commit_sha_repo_id_not_in_key(self) -> None:
        """Có SHA → repo_id không tham gia key; fork cùng SHA = same evidence."""
        ref_pub = EvidenceRef(
            file_path="src/main.py",
            repository_id=1,
            commit_sha="abc123",
            finding_type="architecture",
            classification="api_layer",
            confidence_score=0.9,
        )
        ref_priv = EvidenceRef(
            file_path="src/main.py",
            repository_id=2,  # repo khác nhưng cùng SHA
            commit_sha="abc123",
            finding_type="architecture",
            classification="api_layer",
            confidence_score=0.9,
        )
        # Cùng SHA + cùng path → phải có cùng dedup_key
        assert ref_pub.dedup_key == ref_priv.dedup_key
