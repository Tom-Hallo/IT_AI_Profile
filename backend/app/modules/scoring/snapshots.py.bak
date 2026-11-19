"""Build language scoring snapshots from report-bound GitHub evidence."""

from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.analysis.filters import is_ignored_path, is_safe_path
from app.modules.analysis.languages import EXTENSION_TO_LANGUAGE
from app.modules.analysis.models import AnalysisReport, VerificationEvidence
from app.modules.analysis.schemas import RepositoryVerificationResponse
from app.modules.scoring.engine import Metric, calculate
from app.modules.scoring.models import RubricVersion, SkillScore

VERSION = "2.0.0"


def language_metrics(
    rows: list[VerificationEvidence], language: str
) -> dict[str, Metric]:
    commits = {}
    prs = {}
    for row in rows:
        if row.verification_status != "verified" or row.is_bot or row.is_fork_inherited:
            continue
        if row.evidence_type == "commit" and row.is_merge:
            continue
        changes = [
            item
            for item in (row.metadata_ or {}).get("changed_files", [])
            if is_safe_path(item["path"])
            and not is_ignored_path(item["path"])
            and EXTENSION_TO_LANGUAGE.get(PurePosixPath(item["path"]).suffix.lower())
            == language
        ]
        if changes and row.evidence_type == "commit":
            commits[row.id] = changes
        elif changes and row.evidence_type == "pull_request":
            prs[row.id] = changes
    metrics = {}
    if commits:
        ids = tuple(commits)
        changed_lines = sum(
            item["changes"] for files in commits.values() for item in files
        )
        paths = {item["path"] for files in commits.values() for item in files}
        metrics.update(
            code_contribution=Metric(min(changed_lines / 200, 1), ids),
            commit_frequency=Metric(min(len(commits) / 10, 1), ids),
            complexity=Metric(min(len(paths) / 8, 1), ids),
        )
    if prs:
        metrics["pr_contribution"] = Metric(min(len(prs) / 5, 1), tuple(prs))
    if commits and prs:
        metrics["confidence"] = Metric(
            min((len(commits) + len(prs)) / 8, 1), tuple(commits) + tuple(prs)
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
    rubrics = {
        item.kind: item.id
        for item in db.scalars(
            select(RubricVersion).where(RubricVersion.version == VERSION)
        )
    }
    if not rubrics:
        return
    existing = set(
        db.execute(
            select(SkillScore.kind, SkillScore.technology).where(
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
    for kind, technologies in (
        ("language", report.languages),
        ("framework", report.frameworks),
    ):
        for name in dict.fromkeys(
            item["name"] for item in technologies if item.get("name")
        ):
            if kind not in rubrics or (kind, name) in existing:
                continue
            metrics = language_metrics(rows, name) if kind == "language" else {}
            score = calculate(metrics, rubric_version=VERSION)
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
                    "Chưa xác minh đóng góp cá nhân theo framework."
                )
            db.add(
                SkillScore(
                    user_id=result.user_id,
                    repository_id=report.repository_id,
                    report_id=report.id,
                    rubric_id=rubrics[kind],
                    commit_sha=report.commit_sha,
                    kind=kind,
                    technology=name[:100],
                    status=score["status"],
                    score=round(score["score"]) if score["score"] is not None else None,
                    breakdown=score["breakdown"],
                    explanation=explanation,
                )
            )
