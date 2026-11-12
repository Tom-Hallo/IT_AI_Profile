"""Chống tăng điểm giả (PBI-017): số liệu hoạt động không phải bằng chứng năng lực."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.scoring import (
    EvidenceRef,
    RoleScoringEngine,
    RoleScoringInput,
    ScoreStatus,
    SkillScoreItem,
)
from tests.ai.scoring.conftest import (
    FIXED_NOW,
    arch_ref,
    arch_set,
    backend_full,
    skill,
    snapshot,
)

FORBIDDEN_KEYS = [
    "commit_count",
    "commits",
    "lines_of_code",
    "loc",
    "repository_count",
    "repo_count",
    "stars",
    "forks",
    "fork_count",
]


@pytest.fixture
def engine() -> RoleScoringEngine:
    return RoleScoringEngine(clock=lambda: FIXED_NOW)


def _core(result):
    """Phần kết quả phải bất biến khi chỉ có số liệu hoạt động thay đổi."""
    return (
        result.status,
        result.role_score,
        result.coverage,
        result.confidence,
        [(c.key, c.status, c.score, c.confidence) for c in result.criteria],
        [r.dedup_key for r in result.evidence_refs],
    )


@pytest.mark.parametrize("key", FORBIDDEN_KEYS)
@pytest.mark.parametrize("value", [1, 10_000, 10_000_000])
def test_activity_metric_as_skill_item_does_not_change_score(engine, key, value):
    base = backend_full()
    baseline = engine.score(base)

    inflated = base.model_copy(deep=True)
    inflated.skill_snapshot.items.append(
        SkillScoreItem(
            skill_key=key,
            score=100,
            confidence=100,
            evidence_refs=[
                EvidenceRef(evidence_id=f"{key}-{value}", file_path=f"{key}.txt")
            ],
        )
    )
    result = engine.score(inflated)

    assert _core(result) == _core(baseline)
    assert any(lim.code == "FORBIDDEN_SKILL_KEY" for lim in result.limitations)


@pytest.mark.parametrize("key", FORBIDDEN_KEYS)
def test_activity_metric_as_architecture_evidence_is_ignored(engine, key):
    base = backend_full()
    baseline = engine.score(base)

    inflated = base.model_copy(deep=True)
    inflated.architecture.evidence.append(
        EvidenceRef(
            repository_id=1,
            commit_sha="a" * 40,
            file_path="backend/app/api/router.py",
            finding_type=key,
            classification="api_service",
            confidence_score=1.0,
        )
    )
    result = engine.score(inflated)

    assert _core(result) == _core(baseline)
    assert any(lim.code == "FORBIDDEN_EVIDENCE_TYPE" for lim in result.limitations)


@pytest.mark.parametrize(
    "extra", ["commit_count", "lines_of_code", "repo_count", "stars", "forks_count"]
)
def test_dto_has_no_field_to_carry_activity_metrics(extra):
    with pytest.raises(ValidationError):
        SkillScoreItem(skill_key="python", score=50, confidence=50, **{extra: 999})
    with pytest.raises(ValidationError):
        snapshot([skill("python")], **{extra: 999})
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="e", **{extra: 999})


def test_ten_thousand_commits_without_new_evidence_do_not_raise_score(engine):
    """Mô phỏng 'tăng commit': phía PBI-016 chỉ thêm item thô, không có evidence."""
    base = backend_full()
    baseline = engine.score(base)
    more = base.model_copy(deep=True)
    more.skill_snapshot.items.append(
        SkillScoreItem(
            skill_key="commit_count",
            score=100,
            confidence=100,
            evidence_refs=[EvidenceRef(evidence_id="c", file_path="c")],
        )
    )
    assert engine.score(more).role_score == baseline.role_score


def test_same_evidence_repeated_many_times_counts_once(engine):
    base = backend_full()
    baseline = engine.score(base)

    padded = base.model_copy(deep=True)
    padded.architecture.evidence.extend(
        arch_ref("api_service", "backend/app/api/router.py") for _ in range(50)
    )
    api_item = next(i for i in padded.skill_snapshot.items if i.skill_key == "python")
    api_item.evidence_refs.extend(api_item.evidence_refs[0] for _ in range(50))
    result = engine.score(padded)

    assert _core(result) == _core(baseline)
    assert len(result.criterion("api_service_design").evidence_refs) == 1
    assert len(result.criterion("backend_language").evidence_refs) == 1


def test_duplicate_evidence_cannot_satisfy_minimum_evidence(engine):
    """Cùng một evidence nhân bản không được coi là nhiều bằng chứng."""
    data = RoleScoringInput(
        role_key="backend_developer",
        skill_snapshot=snapshot([skill("python", 80)]),
        architecture=arch_set([arch_ref("api_service") for _ in range(20)]),
    )
    rubric = engine.registry.get("backend_developer")
    crit = next(c for c in rubric.criteria if c.key == "api_service_design")
    need = crit.minimum_evidence.min_evidence_refs
    result = engine.score(data)
    api = result.criterion("api_service_design")
    assert len(api.evidence_refs) == 1
    if need > 1:
        assert api.status == ScoreStatus.INSUFFICIENT


def test_fork_copy_of_same_commit_and_file_is_not_counted_twice(engine):
    """Fork có cùng commit SHA + file_path = cùng nội dung → không thêm bằng chứng."""
    base = backend_full()
    baseline = engine.score(base)

    forked = base.model_copy(deep=True)
    forked.architecture.evidence = [
        *forked.architecture.evidence,
        *[
            ref.model_copy(update={"repository_id": 2, "confidence_score": 0.99})
            for ref in base.architecture.evidence
        ],
    ]
    result = engine.score(forked)

    assert _core(result) == _core(baseline)
    for key in ("api_service_design", "layered_structure"):
        assert len(result.criterion(key).evidence_refs) == 1
        assert any(
            e.reason == "DUPLICATE" for e in result.criterion(key).excluded_evidence
        )


@pytest.mark.parametrize("fork_confidence", [0.7, 0.85, 0.95])
def test_fork_duplicate_never_raises_score_or_confidence(engine, fork_confidence):
    """Trong ngưỡng: giữ giá trị thận trọng. Vượt ngưỡng: CONFLICTING, không tăng."""
    original = [arch_ref("api_service", "backend/app/api/router.py", confidence=0.6)]
    fork = [
        arch_ref(
            "api_service", "backend/app/api/router.py", confidence=fork_confidence
        ).model_copy(update={"repository_id": 2})
    ]

    def run(refs):
        return engine.score(
            RoleScoringInput(
                role_key="backend_developer",
                skill_snapshot=snapshot([skill("python", 80)]),
                architecture=arch_set(refs),
            )
        ).criterion("api_service_design")

    alone, with_fork = run(original), run(original + fork)
    if with_fork.status == ScoreStatus.SCORED:
        assert with_fork.confidence == alone.confidence
        assert with_fork.score == alone.score
    else:
        assert with_fork.status == ScoreStatus.CONFLICTING
        assert with_fork.score is None


def test_same_path_in_different_commits_is_distinct_evidence():
    a = arch_ref("api_service", "x.py", commit="a" * 40)
    b = arch_ref("api_service", "x.py", commit="b" * 40)
    assert a.dedup_key != b.dedup_key


def test_same_path_without_commit_in_different_repos_is_distinct_evidence():
    """Không có SHA thì không thể chứng minh cùng nội dung → giữ tách biệt."""
    a = EvidenceRef(
        repository_id=1,
        file_path="x.py",
        finding_type="architecture",
        classification="api_service",
    )
    b = a.model_copy(update={"repository_id": 2})
    assert a.dedup_key != b.dedup_key


def test_more_repositories_without_new_evidence_do_not_change_score(engine):
    base = backend_full()
    baseline = engine.score(base)
    many = base.model_copy(deep=True)
    many.skill_snapshot.repository_ids = [str(i) for i in range(1, 60)]
    many.architecture.repository_ids = [str(i) for i in range(1, 60)]
    assert _core(engine.score(many)) == _core(baseline)
