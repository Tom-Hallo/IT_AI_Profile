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
        id=10,
        confidence="high",
        file_path="api.py",
        finding_type="architecture",
        classification="api_service",
        evidence_source="source_code",
    )
    assert score([changed], [finding])["architecture"] == 33
    finding.file_path = "unrelated.py"
    assert score([changed], [finding])["architecture"] is None


def test_configuration_and_peer_review_need_independent_evidence():
    config = event(
        metadata_={"changed_files": [{"path": "tests/conftest.py", "changes": 1}]}
    )
    assert score([config])["testing"] == 50
    review = SimpleNamespace(
        id=2,
        evidence_type="review",
        is_profile_owner=True,
        actor_type="User",
        pr_number=12,
        state="APPROVED",
        target_identifier="Review #2",
    )
    external = SimpleNamespace(
        id=3,
        evidence_type="pull_request",
        is_profile_owner=False,
        actor_type="User",
        pr_number=12,
        target_identifier="PR #12",
    )
    assert score([], collab=[review])["collaboration"] is None
    assert score([], collab=[external, review])["collaboration"] == 33


def test_structural_architecture_accepts_exact_source_file_not_sibling():
    path = "backend/app/api/router.py"
    changed = event(metadata_={"changed_files": [{"path": path, "changes": 3}]})
    finding = SimpleNamespace(
        id=11,
        confidence="high",
        file_path=path,
        finding_type="architecture",
        classification="layered_architecture",
        evidence_source="directory_structure",
    )
    assert score([changed], [finding])["architecture"] == 33
    finding.file_path = "backend/app/api"
    assert score([changed], [finding])["architecture"] == 33
    finding.file_path = "backend/app/api/other.py"
    assert score([changed], [finding])["architecture"] is None
    finding.file_path = path
    changed.is_merge = True
    assert score([changed], [finding])["architecture"] is None
