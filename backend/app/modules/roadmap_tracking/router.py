"""PBI-024 API; all roadmap access is user-scoped."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.roadmaps.models import Roadmap
from app.modules.users.models import User

from .adapters import SnapshotNotFound, snapshot_provider
from .engine import IncomparableSnapshot, evaluate
from .models import Milestone, MilestoneHistory, RoadmapSuggestion

router = APIRouter(prefix="/roadmap-tracking", tags=["Roadmap Tracking"])
DB = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Status = Literal["pending", "in_progress", "completed"]


class StatusUpdate(BaseModel):
    status: Status
    note: str | None = Field(default=None, max_length=2000)
    expected_version: int = Field(ge=1)


class ReevaluateRequest(BaseModel):
    snapshot_id: str = Field(min_length=1, max_length=128)
    expected_scope: str = Field(min_length=1, max_length=128)
    expected_rubric: str = Field(min_length=1, max_length=128)
    expected_period: str = Field(min_length=1, max_length=128)


def owned_roadmap(db: Session, user: User, roadmap_id: int) -> Roadmap:
    roadmap = db.scalar(
        select(Roadmap).where(Roadmap.id == roadmap_id, Roadmap.user_id == user.id)
    )
    if roadmap is None:
        raise HTTPException(404, "Roadmap not found")
    return roadmap


def serialize_milestone(m: Milestone) -> dict:
    return {
        "id": m.id,
        "external_key": m.external_key,
        "title": m.title,
        "required_skills": m.required_skills,
        "status": m.status,
        "version": m.version,
    }


def serialize_suggestion(s: RoadmapSuggestion) -> dict:
    return {
        "id": s.id,
        "milestone_id": s.milestone_id,
        "snapshot_id": s.snapshot_key,
        "action": s.action,
        "explanation": s.explanation,
        "evidence": s.evidence,
        "state": s.state,
    }


@router.get("/{roadmap_id}")
def get_tracking(roadmap_id: int, user: CurrentUser, db: DB):
    owned_roadmap(db, user, roadmap_id)
    milestones = db.scalars(
        select(Milestone)
        .where(Milestone.roadmap_id == roadmap_id)
        .order_by(Milestone.id)
    ).all()
    suggestions = db.scalars(
        select(RoadmapSuggestion)
        .where(RoadmapSuggestion.roadmap_id == roadmap_id)
        .order_by(RoadmapSuggestion.id.desc())
    ).all()
    return {
        "milestones": [serialize_milestone(m) for m in milestones],
        "suggestions": [serialize_suggestion(s) for s in suggestions],
    }


@router.get("/{roadmap_id}/milestones/{milestone_id}/history")
def get_history(roadmap_id: int, milestone_id: int, user: CurrentUser, db: DB):
    owned_roadmap(db, user, roadmap_id)
    milestone = db.scalar(
        select(Milestone).where(
            Milestone.id == milestone_id, Milestone.roadmap_id == roadmap_id
        )
    )
    if milestone is None:
        raise HTTPException(404, "Milestone not found")
    entries = db.scalars(
        select(MilestoneHistory)
        .where(MilestoneHistory.milestone_id == milestone_id)
        .order_by(MilestoneHistory.id)
    ).all()
    return [
        {
            "id": h.id,
            "old_status": h.old_status,
            "new_status": h.new_status,
            "note": h.note,
            "source": h.source,
            "created_at": h.created_at,
        }
        for h in entries
    ]


@router.patch("/{roadmap_id}/milestones/{milestone_id}")
def update_milestone(
    roadmap_id: int, milestone_id: int, payload: StatusUpdate, user: CurrentUser, db: DB
):
    owned_roadmap(db, user, roadmap_id)
    m = db.scalar(
        select(Milestone)
        .where(Milestone.id == milestone_id, Milestone.roadmap_id == roadmap_id)
        .with_for_update()
    )
    if m is None:
        raise HTTPException(404, "Milestone not found")
    if m.version != payload.expected_version:
        raise HTTPException(409, "Milestone version conflict")
    if m.status == payload.status:
        return serialize_milestone(m)
    old = m.status
    m.status = payload.status
    m.version += 1
    db.add(
        MilestoneHistory(
            milestone_id=m.id,
            actor_user_id=user.id,
            old_status=old,
            new_status=m.status,
            note=payload.note,
            source="manual",
        )
    )
    db.commit()
    return serialize_milestone(m)


@router.post("/{roadmap_id}/re-evaluate")
def reevaluate(roadmap_id: int, payload: ReevaluateRequest, user: CurrentUser, db: DB):
    roadmap = owned_roadmap(db, user, roadmap_id)
    # Trust the persisted roadmap metadata, never client-supplied compatibility claims.
    metadata = (
        roadmap.data.get("analysis_context", {})
        if isinstance(roadmap.data, dict)
        else {}
    )
    expected = (metadata.get("scope"), metadata.get("rubric"), metadata.get("period"))
    requested = (
        payload.expected_scope,
        payload.expected_rubric,
        payload.expected_period,
    )
    if any(value is None for value in expected) or expected != requested:
        raise HTTPException(422, "Roadmap analysis context missing or mismatched")
    try:
        snapshot = snapshot_provider.get(payload.snapshot_id, user.id)
    except SnapshotNotFound as exc:
        raise HTTPException(404, "Snapshot not found") from exc
    if snapshot.user_id != user.id:
        raise HTTPException(404, "Snapshot not found")
    milestones = db.scalars(
        select(Milestone).where(Milestone.roadmap_id == roadmap_id)
    ).all()
    try:
        proposed = evaluate(
            [serialize_milestone(m) for m in milestones],
            snapshot,
            expected_scope=payload.expected_scope,
            expected_rubric=payload.expected_rubric,
            expected_period=payload.expected_period,
        )
    except IncomparableSnapshot as exc:
        raise HTTPException(422, str(exc)) from exc
    for item in proposed:
        existing = db.scalar(
            select(RoadmapSuggestion).where(
                RoadmapSuggestion.roadmap_id == roadmap_id,
                RoadmapSuggestion.snapshot_key == snapshot.key,
                RoadmapSuggestion.milestone_id == item["milestone_id"],
                RoadmapSuggestion.action == item["action"],
            )
        )
        if existing is None:
            db.add(
                RoadmapSuggestion(
                    roadmap_id=roadmap_id, snapshot_key=snapshot.key, **item
                )
            )
    db.commit()
    suggestions = db.scalars(
        select(RoadmapSuggestion).where(
            RoadmapSuggestion.roadmap_id == roadmap_id,
            RoadmapSuggestion.snapshot_key == snapshot.key,
        )
    ).all()
    return {
        "snapshot_id": snapshot.key,
        "suggestions": [serialize_suggestion(s) for s in suggestions],
    }


def resolve(
    roadmap_id: int,
    suggestion_id: int,
    decision: Literal["applied", "rejected"],
    user: User,
    db: Session,
):
    owned_roadmap(db, user, roadmap_id)
    s = db.scalar(
        select(RoadmapSuggestion)
        .where(
            RoadmapSuggestion.id == suggestion_id,
            RoadmapSuggestion.roadmap_id == roadmap_id,
        )
        .with_for_update()
    )
    if s is None:
        raise HTTPException(404, "Suggestion not found")
    if s.state != "pending":
        raise HTTPException(409, "Suggestion already resolved")
    m = db.scalar(
        select(Milestone)
        .where(Milestone.id == s.milestone_id, Milestone.roadmap_id == roadmap_id)
        .with_for_update()
    )
    if m is None:
        raise HTTPException(409, "Milestone missing")
    if decision == "applied":
        if s.action != "complete":
            raise HTTPException(422, "Unsupported suggestion action")
        if m.status != "completed":
            old = m.status
            m.status = "completed"
            m.version += 1
            db.add(
                MilestoneHistory(
                    milestone_id=m.id,
                    actor_user_id=user.id,
                    old_status=old,
                    new_status="completed",
                    note=f"Applied suggestion {s.id} from snapshot {s.snapshot_key}",
                    source="suggestion",
                )
            )
    s.state = decision
    s.resolved_at = datetime.now(UTC)
    db.commit()
    return serialize_suggestion(s)


@router.post("/{roadmap_id}/suggestions/{suggestion_id}/apply")
def apply_suggestion(roadmap_id: int, suggestion_id: int, user: CurrentUser, db: DB):
    return resolve(roadmap_id, suggestion_id, "applied", user, db)


@router.post("/{roadmap_id}/suggestions/{suggestion_id}/reject")
def reject_suggestion(roadmap_id: int, suggestion_id: int, user: CurrentUser, db: DB):
    return resolve(roadmap_id, suggestion_id, "rejected", user, db)
