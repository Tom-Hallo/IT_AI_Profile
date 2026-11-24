from types import SimpleNamespace

from app.modules.analysis.dashboard_radar import radar_coverage


def event(**overrides):
    return SimpleNamespace(
        **{
            "id": 1,
            "verification_status": "verified",
            "is_bot": False,
            "actor_type": "User",
            "is_fork_inherited": False,
            "evidence_type": "commit",
            "is_merge": False,
            "target_identifier": "abc",
            "pr_merged": False,
            "metadata_": {"changed_files": []},
            **overrides,
        }
    )


def score(events, findings=(), collab=()):
    result = radar_coverage(events, findings, collab, repository_id=7, report_id=9)
    return {axis["key"]: axis["score"] for axis in result["axes"]}


def test_verified_changes_measure_coverage_not_event_volume():
    changed = event(
        metadata_={
            "changed_files": [
                {"path": "src/main.py", "changes": 10},
                {"path": "tests/test_main.py", "changes": 5},
                {"path": ".github/workflows/ci.yml", "changes": 2},
            ]
        }
    )
    assert score([changed, changed]) == {
        "code": 50,
        "architecture": None,
        "testing": 50,
        "collaboration": None,
        "ci": 50,
    }


def test_unverified_or_merge_changes_do_not_award_coverage():
    metadata = {"changed_files": [{"path": "tests/test_main.py", "changes": 5}]}
    assert all(
        value is None
        for value in score(
            [
                event(verification_status="unverified", metadata_=metadata),
                event(is_merge=True, metadata_=metadata),
                event(is_bot=True, metadata_=metadata),
                event(is_fork_inherited=True, metadata_=metadata),
            ]
        ).values()
    )


def test_authored_pr_and_checks_are_distinct_from_proficiency():
    pr = event(evidence_type="pull_request", target_identifier="12", pr_merged=True)
    check = SimpleNamespace(
        id=4,
        evidence_type="check_run",
        is_profile_owner=True,
        actor_type=None,
        pr_number=12,
        commit_sha="abc",
        state="completed",
        conclusion="failure",
        target_identifier="CheckRun #4",
    )
    scores = score([pr], collab=[check])
    assert scores["collaboration"] == 67
    assert scores["ci"] == 50
    assert score([], collab=[check])["ci"] is None


def test_architecture_requires_exact_report_file_overlap():
    changed = event(metadata_={"changed_files": [{"path": "api.py", "changes": 1}]})
    finding = SimpleNamespace(
        confidence="high",
        file_path="api.py",
        finding_type="architecture",
        classification="api_service",
        evidence_source="source_code",
    )
    assert score([changed], [finding])["architecture"] == 33
    finding.file_path = "unrelated.py"
    assert score([changed], [finding])["architecture"] is None
