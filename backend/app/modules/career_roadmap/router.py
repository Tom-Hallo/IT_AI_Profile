"""Authenticated owner-only roadmap endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.github.models import Repository
from app.modules.roadmaps.models import Roadmap
from app.modules.users.models import User

from .engine import generate
from .provider import RealAssessmentProvider

router = APIRouter(prefix="/career-roadmaps", tags=["Career Roadmaps"])


class GenerateRequest(BaseModel):
    goal: Literal["backend", "frontend", "fullstack", "devops"]


def _serialize(item: Roadmap, db: Session, user_id: int) -> dict:
    """Recheck evidence visibility on every read (including after consent revoke)."""
    data = dict(item.data)
    permitted = set(
        db.scalars(
            select(Repository.id).where(
                Repository.owner_id == user_id, Repository.private.is_(False)
            )
        ).all()
    )
    milestones = []
    for original in data.get("milestones", []):
        m = dict(original)
        links = [
            e for e in m.get("evidence", []) if e.get("repository_id") in permitted
        ]
        if len(links) != len(m.get("evidence", [])) or (
            m.get("gap_type") == "skill_gap" and not links
        ):
            m["evidence"] = links
            m["current_score"] = None
            m["confidence"] = "unknown"
            m["gap_type"] = "missing_evidence"
            m["gap"] = None
        milestones.append(m)
    data["milestones"] = milestones
    data["evidence_gaps"] = [
        m["skill"] for m in milestones if m["gap_type"] == "missing_evidence"
    ]
    return {"id": item.id, "title": item.title, "created_at": item.created_at, **data}


@router.post("", status_code=201)
def create_roadmap(
    body: GenerateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    assessments = RealAssessmentProvider().load(db, user.id)
    payload = generate(body.goal, assessments)
    item = Roadmap(
        user_id=user.id,
        title=f"{body.goal.title()} Career Roadmap",
        description="Evidence-based personalized roadmap",
        data=payload,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize(item, db, user.id)


@router.get("")
def list_roadmaps(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    items = db.scalars(
        select(Roadmap)
        .where(Roadmap.user_id == user.id)
        .order_by(Roadmap.created_at.desc(), Roadmap.id.desc())
    ).all()
    return [_serialize(item, db, user.id) for item in items]


@router.get("/{roadmap_id}")
def get_roadmap(
    roadmap_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    item = db.scalar(
        select(Roadmap).where(Roadmap.id == roadmap_id, Roadmap.user_id == user.id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Roadmap not found")
    return _serialize(item, db, user.id)
