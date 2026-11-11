"""Read-only scoring API.

Never score unverified static detections as proficiency.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.analysis.service import (
    verify_private_repo_consent,
    verify_repository_access,
)
from app.modules.users.models import User

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
):
    repo = verify_repository_access(db, repository_id, user)
    verify_private_repo_consent(repo, None, db=db, user_id=user.id)
    query = select(SkillScore).where(
        SkillScore.repository_id == repository_id, SkillScore.user_id == user.id
    )
    if kind:
        query = query.where(SkillScore.kind == kind)
    scores = db.scalars(
        query.order_by(SkillScore.created_at.desc(), SkillScore.id.desc())
        .offset(offset)
        .limit(limit)
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
