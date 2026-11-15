"""Conservative framework attribution regression tests."""

from types import SimpleNamespace

from app.modules.scoring.snapshots import framework_metrics


def evidence(path, source="source_code", framework="FastAPI"):
    return SimpleNamespace(
        file_path=path,
        finding_type="framework",
        classification=framework,
        evidence_source=source,
        confidence="high",
    )


def event(identifier, kind, path, *, verified=True, merge=False, bot=False):
    return SimpleNamespace(
        id=identifier,
        evidence_type=kind,
        verification_status="verified" if verified else "unverified",
        is_bot=bot,
        is_fork_inherited=False,
        is_merge=merge,
        metadata_={"changed_files": [{"path": path, "changes": 100}]},
    )


def test_manifest_detection_never_attributes_personal_framework_skill():
    assert (
        framework_metrics(
            [event(1, "commit", "requirements.txt")],
            "FastAPI",
            [evidence("requirements.txt", "manifest")],
        )
        == {}
    )


def test_framework_requires_exact_source_file_overlap():
    assert (
        framework_metrics(
            [event(1, "commit", "src/unrelated.py")],
            "FastAPI",
            [evidence("src/api.py")],
        )
        == {}
    )


def test_framework_verified_pr_and_commit_metrics_do_not_double_count():
    rows = [
        event(1, "commit", "src/api.py"),
        event(2, "pull_request", "src/api.py"),
        event(3, "commit", "src/api.py", verified=False),
        event(4, "commit", "src/api.py", merge=True),
        event(5, "commit", "src/api.py", bot=True),
    ]
    metrics = framework_metrics(rows, "FastAPI", [evidence("src/api.py")])
    assert metrics["code_contribution"].value == 0.5
    assert metrics["code_contribution"].evidence_ids == (2,)
    assert metrics["commit_frequency"].evidence_ids == (1,)
    assert metrics["pr_contribution"].evidence_ids == (2,)
    assert metrics["confidence"].evidence_ids == (1, 2)


def test_framework_rejects_vendor_and_unsafe_paths():
    assert (
        framework_metrics(
            [event(1, "commit", "vendor/api.py")],
            "FastAPI",
            [evidence("vendor/api.py")],
        )
        == {}
    )
    assert (
        framework_metrics(
            [event(1, "commit", "../api.py")],
            "FastAPI",
            [evidence("../api.py")],
        )
        == {}
    )
