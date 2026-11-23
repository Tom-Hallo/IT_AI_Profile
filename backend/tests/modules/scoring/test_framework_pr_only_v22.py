"""Framework v2.2 scoring uses verified PR or commit without inventing either."""

from types import SimpleNamespace

import pytest

from app.modules.scoring.engine import calculate, calculate_framework
from app.modules.scoring.snapshots import (
    FRAMEWORK_VERSION,
    framework_metrics,
    framework_v22_metrics,
)


def source_evidence(path="src/api.py", kind="source_code"):
    return SimpleNamespace(
        file_path=path,
        finding_type="framework",
        classification="FastAPI",
        evidence_source=kind,
        confidence="high",
    )


def event(
    identifier,
    kind,
    path="src/api.py",
    *,
    verified=True,
    bot=False,
    inherited=False,
    merge=False,
):
    return SimpleNamespace(
        id=identifier,
        evidence_type=kind,
        verification_status="verified" if verified else "unverified",
        is_bot=bot,
        is_fork_inherited=inherited,
        is_merge=merge,
        metadata_={"changed_files": [{"path": path, "changes": 100}]},
    )


def assess(rows, evidence=None, *, files_partial=False):
    raw = framework_metrics(rows, "FastAPI", evidence or [source_evidence()])
    metrics = framework_v22_metrics(raw, scoring_files_partial=files_partial)
    return calculate_framework(metrics, rubric_version=FRAMEWORK_VERSION), metrics


def test_verified_pr_only_scores_without_fabricating_commits():
    result, metrics = assess([event(11, "pull_request"), event(12, "pull_request")])
    assert result["status"] == "Scored"
    assert result["score"] is not None and 0 < result["score"] <= 100
    assert all(set(part["evidence_ids"]) <= {11, 12} for part in result["breakdown"])
    assert metrics["verified_activity"].evidence_ids == (11, 12)
    assert [part["criterion"] for part in result["breakdown"]] == [
        "code_contribution",
        "complexity",
        "verified_activity",
        "confidence",
    ]


def test_verified_commit_only_can_score_independently():
    result, metrics = assess([event(21, "commit")])
    assert result["status"] == "Scored"
    assert metrics["verified_activity"].evidence_ids == (21,)


def test_partial_file_collection_reduces_confidence_not_invents_other_events():
    rows = [event(11, "pull_request"), event(12, "pull_request")]
    full, _ = assess(rows)
    partial, metrics = assess(rows, files_partial=True)
    assert partial["status"] == "Scored"
    assert partial["score"] < full["score"]
    assert metrics["confidence"].value == 0.125


def test_combined_pr_commits_are_not_added_as_distinct_work():
    rows = [
        event(1, "commit"),
        event(2, "commit"),
        event(3, "pull_request"),
    ]
    _, metrics = assess(rows)
    assert metrics["verified_activity"].evidence_ids == (1, 2)
    assert metrics["verified_activity"].value == 2 / 8


def test_unverified_bot_fork_merge_and_unrelated_files_never_score():
    rows = [
        event(1, "pull_request", verified=False),
        event(2, "pull_request", bot=True),
        event(3, "commit", inherited=True),
        event(4, "commit", merge=True),
        event(5, "pull_request", path="src/unrelated.py"),
    ]
    result, _ = assess(rows)
    assert result["status"] == "Insufficient"
    assert result["score"] is None


def test_manifest_evidence_alone_never_proves_personal_skill():
    result, _ = assess([event(1, "pull_request")], [source_evidence(kind="manifest")])
    assert result["score"] is None


def test_legacy_strict_rubric_unchanged():
    raw = framework_metrics([event(1, "pull_request")], "FastAPI", [source_evidence()])
    strict = calculate(raw, rubric_version="2.1.0")
    assert strict["status"] == "Insufficient"
    assert strict["score"] is None


def test_framework_rubric_rejects_invalid_weights():
    _, metrics = assess([event(1, "pull_request")])
    with pytest.raises(ValueError, match="Framework rubric"):
        calculate_framework(
            metrics,
            rubric_version=FRAMEWORK_VERSION,
            weights={
                "code_contribution": 30,
                "complexity": 20,
                "verified_activity": 30,
                "confidence": 10,
            },
        )
