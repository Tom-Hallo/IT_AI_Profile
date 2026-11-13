from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.analysis.models import AnalysisReport
from app.modules.scoring.models import SkillScore
from app.modules.scoring.snapshots import save_skill_snapshots


def test_snapshot_uses_only_verified_changes_in_matching_language():
    def event(id, kind, status, path, changes):
        return SimpleNamespace(
            id=id,
            evidence_type=kind,
            verification_status=status,
            is_bot=False,
            is_merge=False,
            is_fork_inherited=False,
            metadata_={"changed_files": [{"path": path, "changes": changes}]},
        )

    rows = [
        event(1, "commit", "verified", "src/main.py", 100),
        event(2, "pull_request", "verified", "src/main.py", 100),
        event(3, "commit", "unverified", "src/main.py", 1000),
        event(4, "commit", "verified", "other.go", 1000),
    ]
    db = MagicMock()
    db.get.return_value = AnalysisReport(
        id=7,
        repository_id=5,
        commit_sha="a" * 40,
        languages=[{"name": "Python"}, {"name": "Go"}],
        frameworks=[],
        budget={},
    )
    db.scalars.side_effect = [[SimpleNamespace(kind="language", id=1)], rows]
    db.execute.return_value.tuples.return_value = []
    save_skill_snapshots(
        db,
        SimpleNamespace(
            report_id=7,
            repository_id=5,
            user_id=1,
            coverage_status="complete",
            summary_data={},
        ),
        9,
    )
    snapshots = [call.args[0] for call in db.add.call_args_list]
    python, go = snapshots
    assert isinstance(python, SkillScore)
    assert python.status == "Scored" and python.score == 26
    assert python.breakdown[0]["evidence_ids"] == [1]
    assert go.status == "Insufficient" and go.score is None
