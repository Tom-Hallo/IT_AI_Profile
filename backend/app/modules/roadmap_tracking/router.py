"""PBI-024 API; all roadmap access is user-scoped."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.consent.router import csrf
from app.modules.roadmaps.models import Roadmap
from app.modules.users.models import User

from .adapters import current_snapshot
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


class EvidenceSubmission(BaseModel):
    evidence_url: str = Field(min_length=1, max_length=2000)
    note: str | None = Field(default=None, max_length=2000)
    repository_id: int | None = None


class ReevaluateRequest(BaseModel):
    snapshot_id: str = Field(min_length=1, max_length=128)
    expected_scope: str = Field(min_length=1, max_length=128)
    expected_rubric: str = Field(min_length=1, max_length=128)
    expected_period: str = Field(min_length=1, max_length=128)


def owned_roadmap(
    db: Session, user: User, roadmap_id: int, *, lock: bool = False
) -> Roadmap:
    query = select(Roadmap).where(Roadmap.id == roadmap_id, Roadmap.user_id == user.id)
    roadmap = db.scalar(query.with_for_update() if lock else query)
    if roadmap is None:
        raise HTTPException(404, "Roadmap not found")
    return roadmap


def serialize_milestone(m: Milestone, data_milestone: dict | None = None) -> dict:
    res = {
        "id": m.id,
        "external_key": m.external_key,
        "title": m.title,
        "required_skills": m.required_skills,
        "status": m.status,
        "version": m.version,
    }
    if data_milestone:
        res["evidence"] = data_milestone.get("evidence", [])
        res["verification_status"] = data_milestone.get(
            "verification_status", "verified" if m.status == "completed" else "pending"
        )
    return res


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
    roadmap = owned_roadmap(db, user, roadmap_id)
    milestones = db.scalars(
        select(Milestone)
        .where(Milestone.roadmap_id == roadmap_id)
        .order_by(Milestone.id)
    ).all()
    if not milestones and roadmap.data and isinstance(roadmap.data, dict):
        ms_list = roadmap.data.get("milestones", [])
        if not ms_list and roadmap.data.get("steps"):
            ms_list = [
                {
                    "skill": f"step_{idx}",
                    "title": step,
                    "objective": step,
                    "metric": f"Complete: {step}",
                    "status": "pending",
                }
                for idx, step in enumerate(roadmap.data["steps"], 1)
            ]
            roadmap.data["milestones"] = ms_list
            db.commit()
        if ms_list:
            db.add_all(
                [
                    Milestone(
                        roadmap_id=roadmap.id,
                        external_key=m.get("skill") or f"ms_{idx}",
                        title=m.get("title") or m.get("skill") or f"Milestone {idx}",
                        required_skills=m.get("required_skills")
                        or ([m["skill"]] if "skill" in m else []),
                        status=m.get("status", "pending")
                        if m.get("status") in ("pending", "in_progress", "completed")
                        else "pending",
                    )
                    for idx, m in enumerate(ms_list, 1)
                ]
            )
            db.commit()
            milestones = db.scalars(
                select(Milestone)
                .where(Milestone.roadmap_id == roadmap_id)
                .order_by(Milestone.id)
            ).all()

    data_milestones = {
        item.get("skill"): item
        for item in roadmap.data.get("milestones", [])
        if "skill" in item
    }
    suggestions = db.scalars(
        select(RoadmapSuggestion)
        .where(RoadmapSuggestion.roadmap_id == roadmap_id)
        .order_by(RoadmapSuggestion.id.desc())
    ).all()
    return {
        "milestones": [
            serialize_milestone(m, data_milestones.get(m.external_key))
            for m in milestones
        ],
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


@router.patch("/{roadmap_id}/milestones/{milestone_id}", dependencies=[Depends(csrf)])
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


@router.post(
    "/{roadmap_id}/milestones/{milestone_id}/evidence", dependencies=[Depends(csrf)]
)
def submit_milestone_evidence(
    roadmap_id: int,
    milestone_id: int,
    payload: EvidenceSubmission,
    user: CurrentUser,
    db: DB,
):
    import re

    roadmap = owned_roadmap(db, user, roadmap_id, lock=True)
    m = db.scalar(
        select(Milestone)
        .where(Milestone.id == milestone_id, Milestone.roadmap_id == roadmap_id)
        .with_for_update()
    )
    if m is None:
        raise HTTPException(404, "Milestone not found")
    url = payload.evidence_url.strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            422, "URL minh chứng không hợp lệ (cần bắt đầu bằng http:// hoặc https://)"
        )

    is_verified = False
    verification_status = "self_reported"
    explanation = (
        "Đã ghi nhận minh chứng tự nộp (Tự khai báo). "
        "Cần bằng chứng quét từ repository để xác minh."
    )

    gh_match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if gh_match:
        from app.models.github import Repository

        repo_name = f"{gh_match.group(1)}/{gh_match.group(2)}"
        repo = db.scalar(
            select(Repository).where(
                Repository.user_id == user.id, Repository.full_name == repo_name
            )
        )
        if repo:
            is_commit = "/commit/" in url or "/commits/" in url or "/pull/" in url
            if is_commit:
                is_verified = True
                verification_status = "verified"
                explanation = (
                    "Minh chứng đã được đối chiếu và xác nhận "
                    f"từ repository {repo_name}."
                )
            else:
                verification_status = "self_reported"
                explanation = (
                    f"Đã ghi nhận liên kết repository {repo_name}. "
                    "Đang chờ đối soát commit/PR chi tiết."
                )

    data = dict(roadmap.data)
    milestones = list(data.get("milestones", []))
    for item in milestones:
        if item.get("skill") == m.external_key:
            item.setdefault("evidence", [])
            item["evidence"].append(
                {
                    "url": url,
                    "note": payload.note,
                    "source": "submission",
                    "verified": is_verified,
                    "verification_status": verification_status,
                    "submitted_at": datetime.now(UTC).isoformat(),
                }
            )
            if is_verified:
                item["status"] = "completed"
                item["confidence"] = "high"
            break
    roadmap.data = data

    old_status = m.status
    if is_verified and m.status != "completed":
        m.status = "completed"
        m.version += 1
    elif not is_verified and m.status == "pending":
        m.status = "in_progress"
        m.version += 1

    db.add(
        MilestoneHistory(
            milestone_id=m.id,
            actor_user_id=user.id,
            old_status=old_status,
            new_status=m.status,
            note=f"[{verification_status.upper()}] {url}"
            + (f" - {payload.note}" if payload.note else ""),
            source="submission" if not is_verified else "verified",
        )
    )
    db.commit()
    return {
        "milestone_id": m.id,
        "status": m.status,
        "version": m.version,
        "verification_status": verification_status,
        "evidence_url": url,
        "note": payload.note,
        "explanation": explanation,
    }


@router.post("/{roadmap_id}/re-evaluate", dependencies=[Depends(csrf)])
def reevaluate(
    roadmap_id: int, user: CurrentUser, db: DB, payload: ReevaluateRequest | None = None
):
    roadmap = owned_roadmap(db, user, roadmap_id, lock=True)
    metadata = roadmap.data.get("analysis_context", {})
    expected = (metadata.get("scope"), metadata.get("rubric"), metadata.get("period"))
    if not all(expected):
        raise HTTPException(422, "Roadmap analysis context missing")
    if payload and expected != (
        payload.expected_scope,
        payload.expected_rubric,
        payload.expected_period,
    ):
        raise HTTPException(422, "Roadmap analysis context mismatched")

    snapshot = current_snapshot(db, user.id)
    if payload and payload.snapshot_id != snapshot.key:
        raise HTTPException(404, "Snapshot not found")
    target_scores = {
        row["skill"]: row["target_score"]
        for row in roadmap.data.get("milestones", [])
        if "skill" in row and "target_score" in row
    }
    milestones = db.scalars(
        select(Milestone).where(Milestone.roadmap_id == roadmap_id)
    ).all()
    try:
        proposed = evaluate(
            [
                {
                    **serialize_milestone(m),
                    "target_score": target_scores.get(m.external_key),
                }
                for m in milestones
            ],
            snapshot,
            expected_scope=expected[0],
            expected_rubric=expected[1],
            expected_period=expected[2],
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


@router.post(
    "/{roadmap_id}/suggestions/{suggestion_id}/apply", dependencies=[Depends(csrf)]
)
def apply_suggestion(roadmap_id: int, suggestion_id: int, user: CurrentUser, db: DB):
    return resolve(roadmap_id, suggestion_id, "applied", user, db)


@router.post(
    "/{roadmap_id}/suggestions/{suggestion_id}/reject", dependencies=[Depends(csrf)]
)
def reject_suggestion(roadmap_id: int, suggestion_id: int, user: CurrentUser, db: DB):
    return resolve(roadmap_id, suggestion_id, "rejected", user, db)
