"""Transactional evidence linking and safe read policies for PBI-015."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.analysis.finding_models import AnalysisFinding, FindingEvidenceLink
from app.modules.analysis.models import AnalysisEvidence, AnalysisReport
from app.modules.analysis.service import (
    verify_private_repo_consent,
    verify_repository_access,
)


def evidence_identity(row: AnalysisEvidence) -> str:
    parts = (
        str(row.report_id),
        row.commit_sha,
        row.file_path,
        str(row.line_number),
        row.finding_type,
        row.classification,
        row.evidence_source,
        row.detection_method,
    )
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def build_findings(db: Session, report: AnalysisReport) -> None:
    """Called BEFORE the existing save_analysis_result commit; never commits itself."""
    evidence = db.scalars(
        select(AnalysisEvidence).where(AnalysisEvidence.report_id == report.id)
    ).all()
    if (
        db.scalar(
            select(AnalysisFinding.id)
            .where(AnalysisFinding.report_id == report.id)
            .limit(1)
        )
        is not None
    ):
        return
    groups = defaultdict(list)
    for row in evidence:
        groups[(row.finding_type, row.classification)].append(row)
    pending = []
    for (kind, label), rows in groups.items():
        unique = {evidence_identity(r): r for r in rows}
        finding = AnalysisFinding(
            report_id=report.id,
            finding_key=hashlib.sha256(f"{kind}\x1f{label}".encode()).hexdigest(),
            finding_type=kind,
            classification=label,
            rationale=f"Detected {kind}: {label}",
            confidence_score=max(min(max(r.confidence_score for r in rows), 1), 0),
            analyzer_version="pbi012-legacy",
            status="published" if unique else "draft",
        )
        db.add(finding)
        pending.append((finding, unique.values()))
    if pending:
        db.flush()
    for finding, rows in pending:
        for row in rows:
            db.add(
                FindingEvidenceLink(
                    finding_id=finding.id, evidence_id=row.id, report_id=report.id
                )
            )


def find_detail(db: Session, finding_id: int, user):
    row = db.execute(
        select(AnalysisFinding, AnalysisReport)
        .join(AnalysisReport, AnalysisFinding.report_id == AnalysisReport.id)
        .where(AnalysisFinding.id == finding_id, AnalysisFinding.status == "published")
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Finding not found")
    finding, report = row
    try:
        repo = verify_repository_access(db, report.repository_id, user)
        verify_private_repo_consent(repo, scope=None, db=db, user_id=user.id)
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            raise HTTPException(404, "Finding not found") from None
        raise
    items = db.scalars(
        select(AnalysisEvidence)
        .join(
            FindingEvidenceLink, FindingEvidenceLink.evidence_id == AnalysisEvidence.id
        )
        .where(
            FindingEvidenceLink.finding_id == finding.id,
            FindingEvidenceLink.report_id == report.id,
            AnalysisEvidence.report_id == report.id,
            AnalysisEvidence.repository_id == report.repository_id,
        )
        .order_by(AnalysisEvidence.id)
        .limit(200)
    ).all()
    if not items:
        raise HTTPException(409, "Evidence unavailable")
    return finding, report, items
