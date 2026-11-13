import pytest

from app.modules.roadmap_tracking.engine import IncomparableSnapshot, Snapshot, evaluate

MILESTONES = [
    {"id": 10, "status": "in_progress", "required_skills": ["Python", "FastAPI"]},
    {"id": 11, "status": "completed", "required_skills": ["Python"]},
]


def snapshot(**kwargs):
    data = dict(
        key="s1",
        user_id=1,
        scope="public",
        rubric="v1",
        period="last-90-days",
        skills={
            "Python": [{"verified": True, "ref": "commit:a"}],
            "FastAPI": [{"verified": True, "ref": "commit:b"}],
        },
    )
    data.update(kwargs)
    return Snapshot(**data)


def run(s):
    return evaluate(
        MILESTONES,
        s,
        expected_scope="public",
        expected_rubric="v1",
        expected_period="last-90-days",
    )


def test_verified_evidence_generates_only_unfinished_suggestion():
    result = run(snapshot())
    assert len(result) == 1
    assert result[0]["milestone_id"] == 10
    assert len(result[0]["evidence"]) == 2


def test_missing_evidence_not_completed():
    assert (
        run(snapshot(skills={"Python": [{"verified": True, "ref": "commit:a"}]})) == []
    )


def test_unverified_evidence_not_completed():
    assert (
        run(snapshot(skills={"Python": [{"verified": False, "ref": "commit:a"}]})) == []
    )


@pytest.mark.parametrize(
    "overrides",
    [{"rubric": "v2"}, {"scope": "private"}, {"period": "last-year"}, {"valid": False}],
)
def test_incomparable_snapshot_rejected(overrides):
    with pytest.raises(IncomparableSnapshot):
        run(snapshot(**overrides))


def test_repeat_evaluation_is_deterministic():
    assert run(snapshot()) == run(snapshot())
