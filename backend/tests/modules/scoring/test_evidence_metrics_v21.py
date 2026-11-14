"""Conservative PR evidence regression tests."""

from types import SimpleNamespace

import pytest

from app.modules.scoring.engine import Metric, calculate
from app.modules.scoring.snapshots import language_metrics


def evidence(identifier, kind, path="src/main.py", changes=100, **overrides):
    values = dict(
        id=identifier,
        evidence_type=kind,
        verification_status="verified",
        is_bot=False,
        is_merge=False,
        is_fork_inherited=False,
        metadata_={"changed_files": [{"path": path, "changes": changes}]},
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_pr_only_is_partial_not_fabricated_commit():
    metrics = language_metrics([evidence(1, "pull_request")], "Python")
    assert metrics["code_contribution"].value == 0.5
    assert metrics["complexity"].value == 0.125
    assert metrics["pr_contribution"].value == 0.2
    assert "commit_frequency" not in metrics
    assert calculate(metrics)["status"] == "Insufficient"


def test_merge_commit_does_not_establish_frequency():
    metrics = language_metrics([evidence(1, "commit", is_merge=True)], "Python")
    assert metrics == {}


def test_pr_and_commit_diff_not_summed():
    metrics = language_metrics(
        [
            evidence(1, "commit", changes=100),
            evidence(2, "pull_request", changes=100),
        ],
        "Python",
    )
    assert metrics["code_contribution"].value == 0.5
    assert metrics["code_contribution"].evidence_ids == (2,)
    assert metrics["commit_frequency"].evidence_ids == (1,)


def test_bad_file_metadata_is_ignored():
    metrics = language_metrics(
        [
            evidence(1, "pull_request", changes="100"),
            evidence(2, "pull_request", path="vendor/main.py"),
            evidence(3, "pull_request", is_bot=True),
        ],
        "Python",
    )
    assert metrics == {}


def test_configurable_weights_and_invalid_metrics():
    metrics = {
        key: Metric(1, (i,))
        for i, key in enumerate(
            (
                "code_contribution",
                "commit_frequency",
                "pr_contribution",
                "complexity",
                "confidence",
            ),
            1,
        )
    }
    assert (
        calculate(
            metrics,
            weights={
                "code_contribution": 20,
                "commit_frequency": 20,
                "pr_contribution": 20,
                "complexity": 20,
                "confidence": 20,
            },
        )["score"]
        == 100
    )
    with pytest.raises(ValueError):
        calculate(metrics, weights={"code_contribution": 100})
    metrics["complexity"] = Metric(float("nan"), (1,))
    with pytest.raises(ValueError):
        calculate(metrics)
