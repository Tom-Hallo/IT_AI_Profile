"""Build language scoring snapshots from report-bound GitHub evidence."""

from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.analysis.filters import is_ignored_path, is_safe_path
from app.modules.analysis.languages import EXTENSION_TO_LANGUAGE
from app.modules.analysis.models import (
    AnalysisEvidence,
    AnalysisReport,
    VerificationEvidence,
)
from app.modules.analysis.schemas import RepositoryVerificationResponse
from app.modules.scoring.engine import Metric, calculate
from app.modules.scoring.models import RubricVersion, SkillScore

VERSION = "2.1.0"
LEGACY_VERSION = "2.0.0"


DEFAULT_SATURATION = {
    "changed_lines": 200,
    "commits": 10,
    "pull_requests": 5,
    "distinct_source_files": 8,
    "verified_events": 8,
}


def _verified_changes(row, language: str) -> list[dict]:
    if row.verification_status != "verified" or row.is_bot or row.is_fork_inherited:
        return []
    if row.evidence_type not in {"commit", "pull_request"}:
        return []
    if row.evidence_type == "commit" and row.is_merge:
        return []
    metadata = row.metadata_ or {}
    files = metadata.get("changed_files", [])
    if not isinstance(files, list) or len(files) > 300:
        return []
    valid = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path, changes = item.get("path"), item.get("changes")
        if not isinstance(path, str) or type(changes) is not int or changes <= 0:
            continue
        if (
            is_safe_path(path)
            and not is_ignored_path(path)
            and EXTENSION_TO_LANGUAGE.get(PurePosixPath(path).suffix.lower())
            == language
        ):
            valid.append({"path": path, "changes": changes})
    return valid


def language_metrics(
    rows: list[VerificationEvidence],
    language: str,
    *,
    saturation: dict | None = None,
) -> dict[str, Metric]:
    """PR evidence supports code scope; it never fabricates commit frequency.

    PR aggregate diffs and commit diffs may overlap: use PR diffs preferentially
    for code volume, while verified non-merge commits independently establish
    commit frequency. Never sum both diff sources.
    """
    thresholds = dict(DEFAULT_SATURATION if saturation is None else saturation)
    if set(thresholds) != set(DEFAULT_SATURATION) or any(
        type(v) is not int or v <= 0 for v in thresholds.values()
    ):
        raise ValueError("Invalid rubric saturation")
    commits, prs = {}, {}
    for row in rows:
        changes = _verified_changes(row, language)
        if changes and row.evidence_type == "commit":
            commits[row.id] = changes
        elif changes and row.evidence_type == "pull_request":
            prs[row.id] = changes
    metrics = {}
    source = prs if prs else commits
    if source:
        ids = tuple(source)
        changed_lines = sum(
            item["changes"] for files in source.values() for item in files
        )
        paths = {item["path"] for files in source.values() for item in files}
        metrics["code_contribution"] = Metric(
            min(changed_lines / thresholds["changed_lines"], 1), ids
        )
        metrics["complexity"] = Metric(
            min(len(paths) / thresholds["distinct_source_files"], 1), ids
        )
    if commits:
        metrics["commit_frequency"] = Metric(
            min(len(commits) / thresholds["commits"], 1), tuple(commits)
        )
    if prs:
        metrics["pr_contribution"] = Metric(
            min(len(prs) / thresholds["pull_requests"], 1), tuple(prs)
        )
    if commits and prs:
        metrics["confidence"] = Metric(
            min((len(commits) + len(prs)) / thresholds["verified_events"], 1),
            tuple(commits) + tuple(prs),
        )
    return metrics


def framework_metrics(
    rows: list[VerificationEvidence],
    framework: str,
    evidence: list[AnalysisEvidence],
    *,
    saturation: dict | None = None,
) -> dict[str, Metric]:
    """Attribute only verified edits to paths with source-level framework proof.

    A dependency declaration or config file establishes repository technology,
    not individual framework usage. Never infer usage from a file extension.
    """
    source_paths = {
        item.file_path
        for item in evidence
        if item.finding_type == "framework"
        and item.classification == framework
        and item.evidence_source == "source_code"
        and item.confidence in {"high", "medium"}
        and is_safe_path(item.file_path)
        and not is_ignored_path(item.file_path)
    }
    if not source_paths:
        return {}
    # Reuse the verified, non-merge, non-bot event policy from language scoring.
    # The language dimension is intentionally not inferred from the framework.
    scoped = []
    for row in rows:
        if row.verification_status != "verified" or row.is_bot or row.is_fork_inherited:
            continue
        if row.evidence_type not in {"commit", "pull_request"}:
            continue
        if row.evidence_type == "commit" and row.is_merge:
            continue
        metadata = row.metadata_ or {}
        files = metadata.get("changed_files", [])
        if not isinstance(files, list) or len(files) > 300:
            continue
        matched = [
            item
            for item in files
            if isinstance(item, dict)
            and item.get("path") in source_paths
            and type(item.get("changes")) is int
            and item["changes"] > 0
        ]
        if matched:
            # No mutation of ORM evidence or its JSON metadata.
            from types import SimpleNamespace

            scoped.append(
                SimpleNamespace(
                    id=row.id,
                    evidence_type=row.evidence_type,
                    metadata_={"changed_files": matched},
                )
            )
    # Same five dimensions and de-dup policy as language metrics, but only
    # source files with direct framework signatures qualify.
    thresholds = dict(DEFAULT_SATURATION if saturation is None else saturation)
    if set(thresholds) != set(DEFAULT_SATURATION) or any(
        type(v) is not int or v <= 0 for v in thresholds.values()
    ):
        raise ValueError("Invalid rubric saturation")
    commits = {
        row.id: row.metadata_["changed_files"]
        for row in scoped
        if row.evidence_type == "commit"
    }
    prs = {
        row.id: row.metadata_["changed_files"]
        for row in scoped
        if row.evidence_type == "pull_request"
    }
    source = prs if prs else commits
    metrics = {}
    if source:
        ids = tuple(source)
        changed_lines = sum(
            item["changes"] for files in source.values() for item in files
        )
        paths = {item["path"] for files in source.values() for item in files}
        metrics["code_contribution"] = Metric(
            min(changed_lines / thresholds["changed_lines"], 1), ids
        )
        metrics["complexity"] = Metric(
            min(len(paths) / thresholds["distinct_source_files"], 1), ids
        )
    if commits:
        metrics["commit_frequency"] = Metric(
            min(len(commits) / thresholds["commits"], 1), tuple(commits)
        )
    if prs:
        metrics["pr_contribution"] = Metric(
            min(len(prs) / thresholds["pull_requests"], 1), tuple(prs)
        )
    if commits and prs:
        metrics["confidence"] = Metric(
            min((len(commits) + len(prs)) / thresholds["verified_events"], 1),
            tuple(commits) + tuple(prs),
        )
    return metrics


def save_skill_snapshots(
    db: Session, result: RepositoryVerificationResponse, verification_id: int
) -> None:
    if result.report_id is None:
        return
    report = db.get(AnalysisReport, result.report_id)
    if (
        not isinstance(report, AnalysisReport)
        or report.repository_id != result.repository_id
    ):
        return
    rubric_rows = list(
        db.scalars(
            select(RubricVersion).where(
                RubricVersion.version.in_((VERSION, LEGACY_VERSION))
            )
        )
    )
    # Prefer the new immutable rubric; keep legacy support for installations
    # that have not applied the new seed migration yet.
    rubrics = {}
    for item in sorted(
        rubric_rows,
        key=lambda rubric: getattr(rubric, "version", LEGACY_VERSION) == VERSION,
        reverse=True,
    ):
        rubrics.setdefault(item.kind, item)
    if not rubrics:
        return
    existing = set(
        db.execute(
            select(SkillScore.kind, SkillScore.technology, SkillScore.rubric_id).where(
                SkillScore.report_id == report.id, SkillScore.user_id == result.user_id
            )
        ).tuples()
    )
    complete = result.coverage_status == "complete" and not report.budget.get(
        "limit_reached"
    )
    rows = (
        list(
            db.scalars(
                select(VerificationEvidence)
                .where(VerificationEvidence.verification_id == verification_id)
                .order_by(VerificationEvidence.id)
            )
        )
        if complete
        else []
    )
    # Static evidence must belong to this exact report and commit.
    framework_evidence = []
    if (
        complete
        and report.frameworks
        and rubrics.get("framework")
        and (getattr(rubrics["framework"], "version", LEGACY_VERSION) == VERSION)
    ):
        framework_evidence = list(
            db.scalars(
                select(AnalysisEvidence).where(
                    AnalysisEvidence.report_id == report.id,
                    AnalysisEvidence.repository_id == report.repository_id,
                    AnalysisEvidence.commit_sha == report.commit_sha,
                    AnalysisEvidence.finding_type == "framework",
                )
            )
        )
    for kind, technologies in (
        ("language", report.languages),
        ("framework", report.frameworks),
    ):
        for name in dict.fromkeys(
            item["name"] for item in technologies if item.get("name")
        ):
            if kind not in rubrics or (kind, name, rubrics[kind].id) in existing:
                continue
            rubric = rubrics[kind]
            criteria_value = getattr(rubric, "criteria", None)
            criteria = criteria_value if isinstance(criteria_value, dict) else {}
            weights = criteria.get("weights")
            saturation = criteria.get("saturation")
            metrics = (
                language_metrics(rows, name, saturation=saturation)
                if kind == "language"
                else (
                    framework_metrics(
                        rows, name, framework_evidence, saturation=saturation
                    )
                    if getattr(rubric, "version", LEGACY_VERSION) == VERSION
                    else {}
                )
            )
            score = calculate(
                metrics,
                rubric_version=getattr(rubric, "version", LEGACY_VERSION),
                weights=weights,
            )
            for part in score["breakdown"]:
                part["evidence_kind"] = "verification"
            explanation = score["explanation"]
            if score["score"] is not None:
                explanation = (
                    "Dựa trên commit và PR đã xác minh. Độ phức tạp dùng số tệp "
                    "nguồn khác nhau đã sửa làm chỉ báo phạm vi thay đổi."
                )
            elif kind == "framework":
                explanation = (
                    "Phát hiện framework trong repo. "
                    "Chưa có đủ verified commits/PRs trên tệp có bằng chứng "
                    "framework từ source code."
                )
            db.add(
                SkillScore(
                    user_id=result.user_id,
                    repository_id=report.repository_id,
                    report_id=report.id,
                    rubric_id=rubric.id,
                    commit_sha=report.commit_sha,
                    kind=kind,
                    technology=name[:100],
                    status=score["status"],
                    score=round(score["score"]) if score["score"] is not None else None,
                    breakdown=score["breakdown"],
                    explanation=explanation,
                )
            )
