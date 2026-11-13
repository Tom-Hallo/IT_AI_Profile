from app.modules.historical.compare import SnapshotView, compare_snapshots


def sample(**overrides):
    data = dict(scope={"repos": ["r1"]}, rubric_version="v1", window_start="2026-01-01", window_end="2026-02-01", score=70, skills={"python": 60.0, "sql": 50.0})
    data.update(overrides)
    return SnapshotView(**data)


def test_delta_exact():
    result = compare_snapshots(sample(), sample(score=85, skills={"python": 75.0, "sql": 45.0}))
    assert result["comparable"] is True
    assert result["score_delta"] == 15
    assert result["skill_deltas"] == {"python": 15.0, "sql": -5.0}


def test_rubric_mismatch_blocks_delta():
    result = compare_snapshots(sample(), sample(rubric_version="v2"))
    assert result["score_delta"] is None
    assert "RUBRIC_CHANGED" in result["warnings"]


def test_scope_time_mismatch_blocks_delta():
    result = compare_snapshots(sample(), sample(scope={"repos": ["r2"]}, window_end="2026-03-01"))
    assert set(result["warnings"]) == {"SCOPE_CHANGED", "TIME_WINDOW_CHANGED"}


def test_added_removed_skills():
    result = compare_snapshots(sample(), sample(skills={"python": 65.0, "docker": 50.0}))
    assert result["added_skills"] == ["docker"]
    assert result["removed_skills"] == ["sql"]
