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
    ordered = query.order_by(SkillScore.created_at.desc(), SkillScore.id.desc())
    if report is None:
        return [
            _serialize_score(item)
            for item in db.scalars(ordered.offset(offset).limit(limit)).all()
        ]

    saved = {}
    for item in db.scalars(ordered).all():
        saved.setdefault((item.kind, item.technology), _serialize_score(item))
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
    for category, name in technologies:
        saved.setdefault(
            (category, name),
            {
                "id": None,
                "technology": name,
                "kind": category,
                "rubric_id": None,
                "report_id": report.id,
                "commit_sha": report.commit_sha,
                **missing,
            },
        )
    return list(saved.values())[offset : offset + limit]


def _serialize_score(score: SkillScore) -> dict:
    return {
        "id": score.id,
        "technology": score.technology,
        "kind": score.kind,
        "status": score.status,
        "score": score.score,
        "rubric_id": score.rubric_id,
        "report_id": score.report_id,
        "commit_sha": score.commit_sha,
        "breakdown": score.breakdown,
        "explanation": score.explanation,
    }
