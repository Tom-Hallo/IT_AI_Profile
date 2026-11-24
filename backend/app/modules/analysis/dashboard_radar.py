"""Proposed, versioned radar rubric: coverage of observed contribution evidence.

Coverage is not a proficiency rating. Missing evidence is unknown, not failure.
"""

from collections.abc import Iterable
from typing import Any

RUBRIC_VERSION = "github-evidence-coverage-v1"
RUBRIC = {
    "code": ("source_change", "framework_source"),
    "architecture": ("service_design", "data_design", "structure_design"),
    "testing": ("test_change", "test_config"),
    "collaboration": ("authored_pr", "merged_pr", "peer_review"),
    "ci": ("workflow_change", "completed_check"),
}

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".cs",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".php",
    ".rb",
    ".kt",
    ".swift",
    ".vue",
    ".html",
    ".css",
    ".sql",
    ".scala",
    ".dart",
    ".svelte",
}
TEST_CONFIGS = {
    "pytest.ini",
    "conftest.py",
    "jest.config.js",
    "jest.config.ts",
    "jest.config.mjs",
    "vitest.config.js",
    "vitest.config.ts",
    "vitest.config.mjs",
    "playwright.config.ts",
    "playwright.config.js",
    "tox.ini",
    ".coveragerc",
    "phpunit.xml",
    "phpunit.xml.dist",
}


def _is_source(path: str) -> bool:
    return any(path.lower().endswith(ext) for ext in SOURCE_EXTENSIONS)


def _is_test(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return _is_source(path) and (
        any(
            part in {"test", "tests", "__tests__", "spec", "specs"}
            for part in parts[:-1]
        )
        or name.startswith("test_")
        or name.endswith("_test.go")
        or any(token in name for token in (".test.", ".spec.", "_test.", "_spec."))
    )


def _is_workflow(path: str) -> bool:
    path = path.lower()
    return (
        path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))
    ) or path in {".gitlab-ci.yml", "jenkinsfile", "azure-pipelines.yml"}


def _paths(event: Any) -> Iterable[str]:
    metadata = event.metadata_ or {}
    files = metadata.get("changed_files", []) if isinstance(metadata, dict) else []
    if not isinstance(files, list):
        return
    for item in files:
        if not isinstance(item, dict):
            continue
        path, changes = item.get("path"), item.get("changes")
        if isinstance(path, str) and type(changes) is int and changes > 0:
            yield path


def radar_coverage(
    verification: Iterable[Any],
    findings: Iterable[Any],
    collaboration: Iterable[Any],
    *,
    repository_id: int,
    report_id: int,
) -> dict:
    """Match static findings only to files in verified commits or authored PRs."""
    observed: dict[str, dict] = {}
    changes: dict[str, Any] = {}
    authored_prs: set[int] = set()

    def record(key: str, event: Any, kind: str, path: str | None = None) -> None:
        observed.setdefault(
            key,
            {
                "repository_id": repository_id,
                "report_id": report_id,
                "evidence_id": event.id,
                "kind": kind,
                "target": event.target_identifier,
                "path": path,
            },
        )

    for event in verification:
        if (
            event.verification_status != "verified"
            or event.is_bot
            or event.actor_type == "Bot"
            or event.is_fork_inherited
            or event.evidence_type not in {"commit", "pull_request"}
        ):
            continue
        if event.evidence_type == "commit" and event.is_merge:
            continue
        if event.evidence_type == "pull_request":
            try:
                pr = int(event.target_identifier)
            except (TypeError, ValueError):
                continue
            if pr <= 0:
                continue
            authored_prs.add(pr)
            record("authored_pr", event, "verification")
            if event.pr_merged is True:
                record("merged_pr", event, "verification")
        for path in _paths(event):
            changes.setdefault(path, event)
            if _is_test(path):
                record("test_change", event, "verification", path)
            elif path.lower().split("/")[-1] in TEST_CONFIGS:
                record("test_config", event, "verification", path)
            elif _is_source(path):
                record("source_change", event, "verification", path)
            if _is_workflow(path):
                record("workflow_change", event, "verification", path)

    findings = list(findings)
    for finding in findings:
        if finding.confidence not in {"high", "medium"}:
            continue
        path = finding.file_path
        event = changes.get(path)
        if event is None:
            continue
        if (
            finding.finding_type == "framework"
            and finding.evidence_source == "source_code"
        ):
            record("framework_source", event, "verification", path)
        elif (
            finding.finding_type == "architecture"
            and finding.evidence_source in {"source_code", "configuration"}
        ):
            groups = {
                "api_service": "service_design",
                "background_workers": "service_design",
                "database_integration": "data_design",
                "database_schema_ddl": "data_design",
                "monorepo": "structure_design",
            }
            key = groups.get(finding.classification)
            if key:
                record(key, event, "verification", path)
    # Directory findings are matched by path prefix, never by repo ownership alone.
    for finding in findings:
        if (
            finding.finding_type == "architecture"
            and finding.confidence in {"high", "medium"}
            and finding.evidence_source == "directory_structure"
            and finding.classification in {"layered_architecture", "mvc_architecture"}
        ):
            prefix = finding.file_path.rstrip("/")
            if not prefix or prefix == ".":
                continue
            for path, event in changes.items():
                if _is_source(path) and path.startswith(prefix + "/"):
                    record("structure_design", event, "verification", path)
                    break

    collab = list(collaboration)
    external_prs = {
        row.pr_number
        for row in collab
        if row.evidence_type == "pull_request"
        and not row.is_profile_owner
        and row.actor_type != "Bot"
        and row.pr_number is not None
    }
    for row in collab:
        if not row.is_profile_owner or row.actor_type == "Bot":
            continue
        if (
            row.evidence_type == "review"
            and row.pr_number in external_prs
            and row.pr_number not in authored_prs
            and row.state in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}
        ):
            record("peer_review", row, "collaboration")
        elif (
            row.pr_number in authored_prs
            and row.commit_sha
            and (
                (
                    row.evidence_type == "check_run"
                    and row.state == "completed"
                    and row.conclusion in {"success", "failure", "timed_out"}
                )
                or (
                    row.evidence_type == "commit_status"
                    and row.state in {"success", "failure", "error"}
                )
            )
        ):
            record("completed_check", row, "collaboration")

    axes = []
    for key, criteria in RUBRIC.items():
        found = sum(criterion in observed for criterion in criteria)
        axes.append(
            {
                "key": key,
                "score": round(found * 100 / len(criteria)) if found else None,
                "criteria": [
                    {"key": criterion, "evidence": observed.get(criterion)}
                    for criterion in criteria
                ],
            }
        )
    return {"rubric_version": RUBRIC_VERSION, "axes": axes}
