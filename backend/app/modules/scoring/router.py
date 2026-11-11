"""Read-only scoring API.

Never score unverified static detections as proficiency.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.github.models import Repository
from app.modules.users.models import User

from .models import SkillScore

router = APIRouter(prefix="/scoring", tags=["Skill Scoring"])


@router.get("/repositories/{repository_id}/skills")
def get_scores(
    repository_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    kind: Literal["language", "framework"] | None = None,
):
    repo = db.scalar(
        select(Repository).where(
            Repository.id == repository_id, Repository.owner_user_id == user.id
        )
    )
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    query = select(SkillScore).where(
        SkillScore.repository_id == repository_id, SkillScore.user_id == user.id
    )
    if kind:
        query = query.where(SkillScore.kind == kind)
    scores = db.scalars(
        query.order_by(SkillScore.created_at.desc(), SkillScore.id.desc())
    ).all()
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
