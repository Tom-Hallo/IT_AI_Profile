"""Test Skill Snapshot Adapter (PBI-017): input hợp lệ/không hợp lệ/thiếu dữ liệu."""

from __future__ import annotations

import pytest

from app.modules.role_scoring.access import AccessDecision
from app.modules.role_scoring.errors import SkillSnapshotSourceError
from app.modules.role_scoring.skill_adapter import (
    RawSkillSnapshot,
    SkillSnapshotAdapter,
    SkillSnapshotStatus,
    UnconfiguredSkillSnapshotSource,
)

USER = 7


class FakeGuard:
    def __init__(self, decisions: dict[int, AccessDecision] | None = None) -> None:
        self.decisions = decisions or {}
        self.calls: list[int] = []

    def check(self, repository_id: int) -> AccessDecision:
        self.calls.append(repository_id)
        return self.decisions.get(repository_id, AccessDecision.ALLOWED)


class FakeSource:
    def __init__(self, raw=None, error: Exception | None = None) -> None:
        self.raw, self.error, self.calls = raw, error, []

    def fetch(self, user_id, *, snapshot_ref=None):
        self.calls.append((user_id, snapshot_ref))
        if self.error:
            raise self.error
        return self.raw


def payload(**overrides) -> dict:
    data = {
        "snapshot_ref": "snap-1",
        "status": "complete",
        "repository_ids": ["1"],
        "items": [
            {
                "skill_key": "Python",
                "score": 80,
                "confidence": 70,
                "status": "scored",
                "evidence_refs": [
                    {"evidence_id": 11, "repository_id": 1, "file_path": "a.py"}
                ],
            }
        ],
    }
    data.update(overrides)
    return data


def load(raw, guard=None, **kw):
    adapter = SkillSnapshotAdapter(FakeSource(raw))
    return adapter.load(USER, guard=guard or FakeGuard(), **kw)


def codes(result) -> set[str]:
    return {i.code for i in result.issues}


def test_valid_payload_is_normalized_and_available():
    result = load(RawSkillSnapshot(USER, payload()))
    assert result.status == SkillSnapshotStatus.AVAILABLE
    assert result.snapshot is not None
    assert result.snapshot.items[0].skill_key == "python"  # chuẩn hoá key
    assert result.snapshot.items[0].evidence_refs[0].evidence_id == "11"
    assert result.issues == []


def test_missing_snapshot_is_reported_not_faked():
    result = load(None)
    assert result.status == SkillSnapshotStatus.MISSING
    assert result.snapshot is None
    assert "SKILL_SNAPSHOT_MISSING" in codes(result)


def test_unconfigured_source_reports_not_configured():
    adapter = SkillSnapshotAdapter(UnconfiguredSkillSnapshotSource())
    result = adapter.load(USER, guard=FakeGuard())
    assert result.status == SkillSnapshotStatus.NOT_CONFIGURED
    assert result.snapshot is None


@pytest.mark.parametrize(
    "bad",
    [
        payload(snapshot_ref=""),  # thiếu ref
        payload(items=[{"skill_key": "python", "score": 150}]),  # ngoài thang
        payload(
            items=[{"skill_key": "python", "status": "scored"}]
        ),  # SCORED không điểm
        payload(items=[{"skill_key": "  ", "score": 1}]),  # key rỗng
        payload(unexpected_field=1),  # extra=forbid
        payload(status="weird"),
    ],
)
def test_invalid_payload_is_rejected_without_echoing_values(bad):
    result = load(RawSkillSnapshot(USER, bad))
    assert result.status == SkillSnapshotStatus.INVALID
    assert result.snapshot is None
    assert "SKILL_SNAPSHOT_INVALID" in codes(result)
    assert "weird" not in result.issues[0].message  # không chép giá trị đầu vào


def test_non_mapping_payload_is_invalid():
    result = load(RawSkillSnapshot(USER, "not-a-dict"))  # type: ignore[arg-type]
    assert result.status == SkillSnapshotStatus.INVALID


def test_mapper_translates_pbi016_shape_without_engine_changes():
    raw = RawSkillSnapshot(USER, {"id": "s9", "rows": [("go", 61.0)]})

    def mapper(p):
        return {
            "snapshot_ref": p["id"],
            "items": [
                {
                    "skill_key": k,
                    "score": s,
                    "confidence": 50,
                    "evidence_refs": [{"evidence_id": "e1", "file_path": "x.go"}],
                }
                for k, s in p["rows"]
            ],
        }

    result = SkillSnapshotAdapter(FakeSource(raw), mapper=mapper).load(
        USER, guard=FakeGuard()
    )
    assert result.status == SkillSnapshotStatus.AVAILABLE
    assert result.snapshot.snapshot_ref == "s9"


def test_mapper_crash_is_invalid_not_500():
    raw = RawSkillSnapshot(USER, {})
    result = SkillSnapshotAdapter(FakeSource(raw), mapper=lambda p: p["missing"]).load(
        USER, guard=FakeGuard()
    )
    assert result.status == SkillSnapshotStatus.INVALID


def test_snapshot_of_another_user_is_forbidden():
    result = load(RawSkillSnapshot(USER + 1, payload()))
    assert result.status == SkillSnapshotStatus.FORBIDDEN
    assert result.snapshot is None


def test_requested_snapshot_ref_must_match():
    result = load(RawSkillSnapshot(USER, payload()), snapshot_ref="other")
    assert result.status == SkillSnapshotStatus.INVALID
    assert "SKILL_SNAPSHOT_REF_MISMATCH" in codes(result)


def test_empty_items_and_missing_evidence_are_flagged_but_kept():
    empty = load(RawSkillSnapshot(USER, payload(items=[], repository_ids=[])))
    assert empty.status == SkillSnapshotStatus.AVAILABLE
    assert "SKILL_SNAPSHOT_HAS_NO_ITEMS" in codes(empty)

    no_ev = load(
        RawSkillSnapshot(
            USER,
            payload(
                repository_ids=[],
                items=[{"skill_key": "python", "score": 70, "confidence": 60}],
            ),
        )
    )
    assert no_ev.status == SkillSnapshotStatus.AVAILABLE
    assert "SKILL_ITEM_WITHOUT_EVIDENCE" in codes(no_ev)


def test_snapshot_referencing_inaccessible_repo_is_dropped_whole():
    guard = FakeGuard({1: AccessDecision.PRIVATE_CONSENT_REQUIRED})
    result = load(RawSkillSnapshot(USER, payload()), guard=guard)
    assert result.status == SkillSnapshotStatus.FORBIDDEN
    assert result.snapshot is None


def test_evidence_ref_repo_not_listed_in_repository_ids_is_also_checked():
    guard = FakeGuard({99: AccessDecision.NOT_FOUND})
    data = payload(repository_ids=[])
    data["items"][0]["evidence_refs"][0]["repository_id"] = 99
    result = load(RawSkillSnapshot(USER, data), guard=guard)
    assert result.status == SkillSnapshotStatus.FORBIDDEN
    assert 99 in guard.calls


def test_non_integer_repository_id_is_invalid():
    result = load(RawSkillSnapshot(USER, payload(repository_ids=["abc"])))
    assert result.status == SkillSnapshotStatus.INVALID


def test_repo_references_without_guard_fail_closed():
    adapter = SkillSnapshotAdapter(FakeSource(RawSkillSnapshot(USER, payload())))
    result = adapter.load(USER, guard=None)
    assert result.status == SkillSnapshotStatus.FORBIDDEN


def test_infrastructure_error_is_not_masked_as_missing():
    adapter = SkillSnapshotAdapter(FakeSource(error=RuntimeError("db down")))
    with pytest.raises(SkillSnapshotSourceError):
        adapter.load(USER, guard=FakeGuard())


def test_oversized_snapshot_is_rejected():
    items = [{"skill_key": f"s{i}", "score": 1} for i in range(501)]
    result = load(RawSkillSnapshot(USER, payload(items=items, repository_ids=[])))
    assert result.status == SkillSnapshotStatus.INVALID


def test_database_skill_snapshot_source_empty(db):
    from app.modules.role_scoring.skill_adapter import DatabaseSkillSnapshotSource

    source = DatabaseSkillSnapshotSource(db)
    assert source.fetch(999) is None


def test_database_skill_snapshot_source_fetches_and_maps(db, world):
    from app.modules.analysis.models import (
        AnalysisEvidence,
        AnalysisReport,
    )
    from app.modules.role_scoring.skill_adapter import DatabaseSkillSnapshotSource
    from app.modules.scoring.models import (
        RubricVersion,
        ScoreEvidenceLink,
        SkillScore,
    )

    user = world.user("coder@x.dev")
    repo = world.repo(user)

    rubric = RubricVersion(id=1, kind="language", version="1.0.0", criteria={"c": 1})
    db.add(rubric)

    report = AnalysisReport(
        id=10,
        repository_id=repo.id,
        commit_sha="a" * 40,
        scope="all",
        structure={},
        languages=[],
        frameworks=[],
        architecture=[],
        budget={},
    )
    db.add(report)
    db.flush()

    ev = AnalysisEvidence(
        id=100,
        report_id=report.id,
        repository_id=repo.id,
        commit_sha="a" * 40,
        file_path="app/main.py",
        finding_type="source_code",
        classification="python",
        evidence_source="source_code",
        detection_method="ast",
        confidence="high",
        confidence_score=0.95,
        rationale="Python source found",
    )
    db.add(ev)
    db.flush()

    score = SkillScore(
        id=50,
        user_id=user.id,
        repository_id=repo.id,
        report_id=report.id,
        rubric_id=rubric.id,
        commit_sha="a" * 40,
        kind="language",
        technology="Python",
        status="Scored",
        score=88,
        breakdown=[{"criterion": "code", "points": 88}],
        explanation="Great python proficiency",
    )
    db.add(score)
    db.flush()

    db.add(ScoreEvidenceLink(id=1, score_id=score.id, evidence_id=ev.id))
    db.commit()

    source = DatabaseSkillSnapshotSource(db)
    raw = source.fetch(user.id)
    assert raw is not None
    assert raw.owner_user_id == user.id

    guard = FakeGuard({repo.id: AccessDecision.ALLOWED})
    adapter = SkillSnapshotAdapter(source)
    res = adapter.load(user.id, guard=guard)
    assert res.status == SkillSnapshotStatus.AVAILABLE
    assert res.snapshot is not None
    assert len(res.snapshot.items) == 1
    item = res.snapshot.items[0]
    assert item.skill_key == "python"
    assert item.score == 88.0
    assert item.status.value == "SCORED"
    assert len(item.evidence_refs) == 1
    assert item.evidence_refs[0].file_path == "app/main.py"
