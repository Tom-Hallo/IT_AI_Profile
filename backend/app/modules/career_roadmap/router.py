"""Authenticated owner-only roadmap endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.consent.router import csrf
from app.modules.roadmap_tracking.evidence_policy import visible_milestone
from app.modules.roadmap_tracking.models import Milestone
from app.modules.roadmaps.models import Roadmap
from app.modules.scoring.snapshots import VERSION
from app.modules.users.models import User

from .engine import generate
from .provider import RealAssessmentProvider, public_repo_ids

router = APIRouter(prefix="/career-roadmaps", tags=["Career Roadmaps"])


class GenerateRequest(BaseModel):
    goal: Literal["backend", "frontend", "fullstack", "devops"]


def _serialize(
    item: Roadmap,
    db: Session,
    user_id: int,
    permitted: set[int] | None = None,
    assessments: list[dict[str, Any]] | None = None,
) -> dict:
    """Recheck evidence visibility on every read (including after consent revoke)."""
    data = dict(item.data) if isinstance(item.data, dict) else {}
    if permitted is None:
        permitted = public_repo_ids(db, user_id)
    if assessments is None:
        assessments = RealAssessmentProvider().load(db, user_id)
    if (
        not data.get("milestones")
        and isinstance(data.get("steps"), list)
        and data["steps"]
    ):
        data.setdefault("goal", "backend")
        data["milestones"] = [
            {
                "skill": f"step_{idx}",
                "target_score": 75,
                "current_score": None,
                "gap": None,
                "gap_type": "missing_evidence",
                "priority": idx,
                "objective": step,
                "metric": f"Complete: {step}",
                "evidence": [],
                "confidence": "unknown",
                "status": "todo",
                "order": idx,
            }
            for idx, step in enumerate(data["steps"], 1)
        ]
    milestones = []
    saved_milestones = data.get("milestones", [])
    if not isinstance(saved_milestones, list):
        saved_milestones = []
    for original in saved_milestones:
        m = dict(original) if isinstance(original, dict) else {}
        m.setdefault("gap_type", "missing_evidence")
        m = visible_milestone(m, permitted, assessments)
        milestones.append(m)
    data["milestones"] = milestones
    data["evidence_gaps"] = [
        m.get("skill")
        for m in milestones
        if m.get("gap_type") == "missing_evidence" and m.get("skill")
    ]
    return {"id": item.id, "title": item.title, "created_at": item.created_at, **data}


@router.post("", status_code=201, dependencies=[Depends(csrf)])
def create_roadmap(
    body: GenerateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    assessments = RealAssessmentProvider().load(db, user.id)
    payload = generate(body.goal, assessments)
    payload["analysis_context"] = {
        "scope": "public",
        "rubric": VERSION,
        "period": "all_time",
    }
    item = Roadmap(
        user_id=user.id,
        title=f"{body.goal.title()} Career Roadmap",
        description="Evidence-based personalized roadmap",
        data=payload,
    )
    db.add(item)
    db.flush()
    db.add_all(
        Milestone(
            roadmap_id=item.id,
            external_key=m["skill"],
            title=m["skill"],
            required_skills=[m["skill"]],
        )
        for m in payload["milestones"]
    )
    db.commit()
    db.refresh(item)
    return _serialize(item, db, user.id, assessments=assessments)


@router.get("")
def list_roadmaps(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    items = db.scalars(
        select(Roadmap)
        .where(Roadmap.user_id == user.id)
        .order_by(Roadmap.created_at.asc(), Roadmap.id.asc())
    ).all()
    permitted = public_repo_ids(db, user.id)
    assessments = RealAssessmentProvider().load(db, user.id)
    return [
        _serialize(item, db, user.id, permitted=permitted, assessments=assessments)
        for item in items
    ]


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
