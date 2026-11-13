from app.modules.career_roadmap.engine import generate


def test_empty_assessments_are_unknown_not_zero():
    result = generate("backend", [])
    assert result["total"] == 5
    assert all(m["current_score"] is None for m in result["milestones"])
    assert all(m["gap_type"] == "missing_evidence" for m in result["milestones"])


def test_verified_skill_gap_and_completed_skill():
    result = generate(
        "backend",
        [
            {
                "skill": "python",
                "score": 40,
                "confidence": "high",
                "evidence": [{"id": 1}],
            },
            {
                "skill": "fastapi",
                "score": 90,
                "confidence": "high",
                "evidence": [{"id": 2}],
            },
        ],
    )
    assert next(m for m in result["milestones"] if m["skill"] == "python")["gap"] == 35
    assert not any(m["skill"] == "fastapi" for m in result["milestones"])


def test_unverified_high_score_still_missing_evidence():
    result = generate(
        "frontend",
        [{"skill": "react", "score": 99, "confidence": "low", "evidence": []}],
    )
    react = next(m for m in result["milestones"] if m["skill"] == "react")
    assert react["gap_type"] == "missing_evidence"
    assert react["current_score"] is None


def test_goals_produce_different_skills():
    assert {m["skill"] for m in generate("devops", [])["milestones"]} != {
        m["skill"] for m in generate("frontend", [])["milestones"]
    }
