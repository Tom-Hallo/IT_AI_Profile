"""Finding detail endpoint. Strict response allowlist, no private source code."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.analysis.finding_models import AnalysisFinding
from app.modules.analysis.finding_service import find_detail
from app.modules.analysis.models import AnalysisReport
from app.modules.analysis.service import (
    verify_private_repo_consent,
    verify_repository_access,
)
from app.modules.users.models import User

router = APIRouter(prefix="/analysis/findings", tags=["Finding Evidence"])


class EvidenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    commit_sha: str
    file_path: str
    line_number: int | None
    evidence_source: str
    detection_method: str
    confidence_score: float


class FindingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    report_id: int
    repository_id: int
    commit_sha: str
    finding_type: str
    classification: str
    rationale: str
    confidence_score: float
    analyzer_version: str
    scope: str
    time_range: dict | None
    evidence: list[EvidenceOut]


@router.get("/{finding_id}", response_model=FindingOut)
def get_finding(
    finding_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> FindingOut:
    finding, report, rows = find_detail(db, finding_id, current_user)
    return FindingOut(
        id=finding.id,
        report_id=report.id,
        repository_id=report.repository_id,
        commit_sha=report.commit_sha,
        finding_type=finding.finding_type,
        classification=finding.classification,
        rationale=finding.rationale,
        confidence_score=finding.confidence_score,
        analyzer_version=finding.analyzer_version,
        scope=report.scope,
        time_range=report.time_range,
        evidence=[
            EvidenceOut(
                id=e.id,
                commit_sha=e.commit_sha,
                file_path=e.file_path,
                line_number=e.line_number,
                evidence_source=e.evidence_source,
                detection_method=e.detection_method,
                confidence_score=e.confidence_score,
            )
            for e in rows
        ],
    )


class FindingSummary(BaseModel):
    id: int
    report_id: int
    finding_type: str
    classification: str
    confidence_score: float
    analyzer_version: str


@router.get("", response_model=list[FindingSummary])
def list_findings(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    repository_id: int = Query(gt=0),
    report_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[FindingSummary]:
    repo = verify_repository_access(db, repository_id, current_user)
    try:
        verify_private_repo_consent(repo, scope=None, db=db, user_id=current_user.id)
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            raise HTTPException(404, "Repository not found") from None
        raise
    query = (
        select(AnalysisFinding)
        .join(AnalysisReport, AnalysisFinding.report_id == AnalysisReport.id)
        .where(
            AnalysisReport.repository_id == repository_id,
            AnalysisFinding.status == "published",
        )
    )
    if report_id is not None:
        query = query.where(AnalysisFinding.report_id == report_id)
    rows = db.scalars(query.order_by(AnalysisFinding.id).limit(limit)).all()
    return [
        FindingSummary.model_validate(
            {
                "id": x.id,
                "report_id": x.report_id,
                "finding_type": x.finding_type,
                "classification": x.classification,
                "confidence_score": x.confidence_score,
                "analyzer_version": x.analyzer_version,
            }
        )
        for x in rows
    ]
