"""Regression tests for rubric version isolation and snapshot idempotence."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.analysis.models import AnalysisReport
from app.modules.scoring.snapshots import save_skill_snapshots


def test_v21_creates_separate_snapshot_from_v20():
    db = MagicMock()
    db.get.return_value = AnalysisReport(
        id=7,
        repository_id=5,
        commit_sha="a" * 40,
        languages=[{"name": "Python"}],
        frameworks=[],
        budget={},
    )
    rubric20 = SimpleNamespace(kind="language", id=10, version="2.0.0", criteria={})
    rubric21 = SimpleNamespace(
        kind="language",
        id=11,
        version="2.1.0",
        criteria={
            "weights": {
                "code_contribution": 20,
                "commit_frequency": 20,
                "pr_contribution": 20,
                "complexity": 20,
                "confidence": 20,
            }
        },
    )
    db.scalars.side_effect = [[rubric20, rubric21], []]
    db.execute.return_value.tuples.return_value = [("language", "Python", 10)]
    result = SimpleNamespace(
        report_id=7, repository_id=5, user_id=1, coverage_status="complete"
    )
    save_skill_snapshots(db, result, 9)
    db.add.assert_called_once()
    score = db.add.call_args.args[0]
    assert score.rubric_id == 11
    assert score.status == "Insufficient"
    assert score.score is None


def test_v21_does_not_duplicate_existing_snapshot():
    db = MagicMock()
    db.get.return_value = AnalysisReport(
        id=7,
        repository_id=5,
        commit_sha="a" * 40,
        languages=[{"name": "Python"}],
        frameworks=[],
        budget={},
    )
    rubric = SimpleNamespace(kind="language", id=11, version="2.1.0", criteria={})
    db.scalars.side_effect = [[rubric], []]
    db.execute.return_value.tuples.return_value = [("language", "Python", 11)]
    save_skill_snapshots(
        db,
        SimpleNamespace(
            report_id=7, repository_id=5, user_id=1, coverage_status="complete"
        ),
        9,
    )
    db.add.assert_not_called()
