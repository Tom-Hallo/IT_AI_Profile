"""Read-only scoring API.

Never score unverified static detections as proficiency.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.analysis.models import AnalysisReport
from app.modules.analysis.service import (
    verify_private_repo_consent,
    verify_repository_access,
)
from app.modules.users.models import User

from .engine import calculate
from .models import SkillScore

router = APIRouter(prefix="/scoring", tags=["Skill Scoring"])


@router.get("/repositories/{repository_id}/skills")
def get_scores(
    repository_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    kind: Literal["language", "framework"] | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    report_id: Annotated[int | None, Query(gt=0)] = None,
):
    repo = verify_repository_access(db, repository_id, user)
    verify_private_repo_consent(repo, None, db=db, user_id=user.id)
    query = select(SkillScore).where(
        SkillScore.repository_id == repository_id, SkillScore.user_id == user.id
    )
    report = None
    if report_id is not None:
        report = db.scalar(
            select(AnalysisReport).where(
                AnalysisReport.id == report_id,
                AnalysisReport.repository_id == repository_id,
            )
        )
        if report is None:
            raise HTTPException(404, "Không tìm thấy báo cáo phân tích.")
        query = query.where(SkillScore.report_id == report_id)
    if kind:
        query = query.where(SkillScore.kind == kind)
    scores = db.scalars(
        query.order_by(SkillScore.created_at.desc(), SkillScore.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    if report is not None and not scores and offset == 0:
        # Static detections identify technology. They cannot prove proficiency.
        missing = calculate({})
        technologies = dict.fromkeys(
            (category, item["name"])
            for category, items in (
                ("language", report.languages),
                ("framework", report.frameworks),
            )
            if kind is None or kind == category
            for item in items
            if item.get("name")
        )
        return [
            {
                "id": None,
                "technology": name,
                "kind": category,
                "rubric_id": None,
                "report_id": report.id,
                "commit_sha": report.commit_sha,
                **missing,
            }
            for category, name in list(technologies)[:limit]
        ]
    return [
        {
            "id": s.id,
            "technology": s.technology,
            "kind": s.kind,
            "status": s.status,
            "score": s.score,
            "rubric_id": s.rubric_id,
            "report_id": s.report_id,
            "commit_sha": s.commit_sha,
            "breakdown": s.breakdown,
            "explanation": s.explanation,
        }
        for s in scores
    ]
