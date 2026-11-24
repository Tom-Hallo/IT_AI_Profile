"""PBI-024 API; all roadmap access is user-scoped."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.career_roadmap.provider import RealAssessmentProvider, public_repo_ids
from app.modules.consent.router import csrf
from app.modules.github.models import Repository, user_repository
from app.modules.roadmaps.models import Roadmap
from app.modules.scoring.snapshots import VERSION
from app.modules.users.models import User

from .adapters import current_snapshot
from .engine import IncomparableSnapshot, evaluate, normalize_rubric
from .evidence_policy import link_key, matching_evidence, visible_milestone
from .evidence_urls import parse_github_evidence_url
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
        submitted = data_milestone.get("evidence")
        if not isinstance(submitted, list):
            submitted = []
        verified_submission = any(
            isinstance(item, dict)
            and item.get("verified") is True
            and item.get("verification_status") == "verified"
            for item in submitted
        )
        verified_evaluation = data_milestone.get(
            "verification_status"
        ) == "verified" and bool(data_milestone.get("evaluation_evidence"))
        res["evidence"] = submitted
        res["verification_status"] = (
            "verified"
            if verified_submission or verified_evaluation
            else "self_reported"
            if any(
                isinstance(item, dict)
                and (item.get("source") == "submission" or item.get("url"))
                for item in submitted
            )
            else "pending"
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
        if not isinstance(ms_list, list):
            ms_list = []
        if (
            not ms_list
            and isinstance(roadmap.data.get("steps"), list)
            and roadmap.data["steps"]
        ):
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
            data = deepcopy(roadmap.data)
            data["milestones"] = ms_list
            roadmap.data = data
            flag_modified(roadmap, "data")
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

    # Match the persisted JSONB array order, independent of row insert IDs.
    # Orphaned legacy tracking rows follow in their original ID order.
    data_items = (
        roadmap.data.get("milestones", []) if isinstance(roadmap.data, dict) else []
    )
    if not isinstance(data_items, list):
        data_items = []
    data_milestones = {}
    position = {}
    for index, item in enumerate(data_items):
        if not isinstance(item, dict):
            continue
        key = str(item.get("skill", "")).strip().lower()
        if key:
            data_milestones.setdefault(key, item)
            position.setdefault(key, index)
    milestones.sort(
        key=lambda m: (
            position.get(str(m.external_key or "").strip().lower(), len(data_items)),
            m.id,
        )
    )
    suggestions = db.scalars(
        select(RoadmapSuggestion)
        .where(RoadmapSuggestion.roadmap_id == roadmap_id)
        .order_by(RoadmapSuggestion.id.desc())
    ).all()
    permitted = public_repo_ids(db, user.id)
    assessments = RealAssessmentProvider().load(db, user.id)
    safe_milestones = []
    for m in milestones:
        item = data_milestones.get(str(m.external_key or "").strip().lower())
        safe_milestones.append(
            serialize_milestone(
                m,
                visible_milestone(item, permitted, assessments, m.required_skills)
                if item
                else None,
            )
        )
    # A stale suggestion must not advertise inaccessible evidence as actionable.
    snapshot = current_snapshot(db, user.id) if suggestions else None
    safe_suggestions = []
    for suggestion in suggestions:
        result = serialize_suggestion(suggestion)
        if snapshot is not None and suggestion.snapshot_key != snapshot.key:
            result["evidence"] = []
            if result["state"] == "pending":
                result["state"] = "stale"
        safe_suggestions.append(result)
    return {"milestones": safe_milestones, "suggestions": safe_suggestions}


@router.get("/{roadmap_id}/milestones/{milestone_id}/history")
def get_history(roadmap_id: int, milestone_id: int, user: CurrentUser, db: DB):
    roadmap = owned_roadmap(db, user, roadmap_id)
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
    permitted = public_repo_ids(db, user.id)
    hidden_links = {
        link_key(entry.get("url", ""))
        for item in (roadmap.data or {}).get("milestones", [])
        if isinstance(item, dict)
        for entry in (item.get("evidence") or [])
        if isinstance(entry, dict)
        and entry.get("repository_id") is not None
        and entry["repository_id"] not in permitted
    }

    def history_note(entry: MilestoneHistory) -> str | None:
        if entry.source in {"submission", "verified"} and entry.note:
            parts = entry.note.split(maxsplit=2)
            if len(parts) > 1 and link_key(parts[1]) in hidden_links:
                return None
        return entry.note

    return [
        {
            "id": h.id,
            "old_status": h.old_status,
            "new_status": h.new_status,
            "note": history_note(h),
            "source": h.source,
            "created_at": h.created_at,
        }
        for h in entries
    ]


@router.patch("/{roadmap_id}/milestones/{milestone_id}", dependencies=[Depends(csrf)])
def update_milestone(
    roadmap_id: int, milestone_id: int, payload: StatusUpdate, user: CurrentUser, db: DB
):
    roadmap = owned_roadmap(db, user, roadmap_id, lock=True)
    m = db.scalar(
        select(Milestone)
        .where(Milestone.id == milestone_id, Milestone.roadmap_id == roadmap_id)
        .with_for_update()
    )
    if m is None:
        raise HTTPException(404, "Milestone not found")
    if m.version != payload.expected_version:
        raise HTTPException(409, "Milestone version conflict")

    data_milestones = {
        str(item.get("skill", "")).lower(): item
        for item in (roadmap.data or {}).get("milestones", [])
        if "skill" in item
    }
    cur_data_m = data_milestones.get(str(m.external_key or "").lower())

    def response() -> dict:
        item = (
            visible_milestone(
                cur_data_m,
                public_repo_ids(db, user.id),
                RealAssessmentProvider().load(db, user.id),
                m.required_skills,
            )
            if cur_data_m
            else None
        )
        return serialize_milestone(m, item)

    if m.status == payload.status:
        return response()
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
    if roadmap.data and isinstance(roadmap.data, dict):
        data = deepcopy(roadmap.data)
        for item in data.get("milestones", []):
            if str(item.get("skill", "")).lower() == str(m.external_key or "").lower():
                item["status"] = m.status
                break
        roadmap.data = data
        flag_modified(roadmap, "data")
        cur_data_m = {
            str(item.get("skill", "")).lower(): item
            for item in data.get("milestones", [])
            if "skill" in item
        }.get(str(m.external_key or "").lower())

    db.commit()
    return response()


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
    url = payload.evidence_url.strip()
    try:
        link = parse_github_evidence_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    roadmap = owned_roadmap(db, user, roadmap_id, lock=True)
    m = db.scalar(
        select(Milestone)
        .where(Milestone.id == milestone_id, Milestone.roadmap_id == roadmap_id)
        .with_for_update()
    )
    if m is None:
        raise HTTPException(404, "Milestone not found")

    repo = db.scalar(
        select(Repository)
        .join(user_repository, Repository.id == user_repository.c.repository_id)
        .where(
            user_repository.c.user_id == user.id,
            func.lower(Repository.full_name) == link.repo_name.lower(),
        )
    )
    data = deepcopy(roadmap.data or {})
    item = next(
        (
            row
            for row in data.get("milestones", [])
            if str(row.get("skill", "")).strip().lower()
            == str(m.external_key or "").strip().lower()
        ),
        None,
    )
    if item is None:
        raise HTTPException(409, "Milestone data missing")
    permitted = public_repo_ids(db, user.id)
    is_verified = bool(
        repo is not None
        and repo.id in permitted
        and matching_evidence(
            link,
            repo.id,
            m.required_skills,
            item.get("target_score"),
            RealAssessmentProvider().load(db, user.id),
        )
    )
    verification_status = "verified" if is_verified else "self_reported"
    explanation = (
        "Đã đối chiếu đóng góp với kỹ năng và điểm mục tiêu của cột mốc."
        if is_verified
        else "Đã lưu liên kết. Chưa đủ minh chứng xác minh kỹ năng và điểm mục tiêu."
    )
    entries = item.setdefault("evidence", [])
    if not isinstance(entries, list):
        entries = []
        item["evidence"] = entries
    key = link_key(url)
    existing = next(
        (
            entry
            for entry in entries
            if isinstance(entry, dict)
            and link_key(entry.get("url", "")) == key
        ),
        None,
    )
    old_status = m.status
    if is_verified:
        m.status = "completed"
    elif m.status == "pending":
        m.status = "in_progress"
    item["status"] = m.status
    if m.status != old_status:
        m.version += 1
    record = {
        "url": url,
        "note": payload.note,
        "source": "submission",
        "verified": is_verified,
        "verification_status": verification_status,
        # Never trust a client-supplied repository ID for authorization.
        "repository_id": repo.id if repo is not None else None,
        "submitted_at": datetime.now(UTC).isoformat(),
    }
    duplicate = existing is not None
    changed = (
        not duplicate
        or existing.get("verified") is not is_verified
        or m.status != old_status
    )
    if not duplicate:
        entries.append(record)
    else:
        existing.update(
            verified=is_verified,
            verification_status=verification_status,
            repository_id=(
                record["repository_id"]
                if record["repository_id"] is not None
                else existing.get("repository_id")
            ),
        )
    roadmap.data = data
    flag_modified(roadmap, "data")
    if changed:
        db.add(
            MilestoneHistory(
                milestone_id=m.id,
                actor_user_id=user.id,
                old_status=old_status,
                new_status=m.status,
                note=f"[{verification_status.upper()}] {url}"
                + (f" - {payload.note}" if payload.note else ""),
                source="verified" if is_verified else "submission",
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
        "duplicate": duplicate,
    }


@router.post("/{roadmap_id}/re-evaluate", dependencies=[Depends(csrf)])
def reevaluate(
    roadmap_id: int, user: CurrentUser, db: DB, payload: ReevaluateRequest | None = None
):
    roadmap = owned_roadmap(db, user, roadmap_id, lock=True)
    metadata = roadmap.data.get("analysis_context", {}) if roadmap.data else {}
    expected_scope = metadata.get("scope") or "public"
    expected_rubric = metadata.get("rubric") or VERSION
    expected_period = metadata.get("period") or "all_time"
    expected = (expected_scope, expected_rubric, expected_period)
    if payload and (
        expected_scope != payload.expected_scope
        or normalize_rubric(expected_rubric)
        != normalize_rubric(payload.expected_rubric)
        or expected_period != payload.expected_period
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
        "evaluation": {
            "source": "stored_public_analysis",
            "checked_milestones": sum(m.status != "completed" for m in milestones),
            "verified_skill_count": sum(
                any(
                    evidence.get("verified") is True and evidence.get("ref")
                    for evidence in items
                )
                for items in snapshot.skills.values()
            ),
        },
    }


def resolve(
    roadmap_id: int,
    suggestion_id: int,
    decision: Literal["applied", "rejected"],
    user: User,
    db: Session,
):
    roadmap = owned_roadmap(db, user, roadmap_id, lock=True)
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
        snapshot = current_snapshot(db, user.id)
        if s.snapshot_key != snapshot.key:
            raise HTTPException(409, "Roadmap suggestion snapshot is stale")
        metadata = (roadmap.data or {}).get("analysis_context", {})
        target = next(
            (
                item.get("target_score")
                for item in (roadmap.data or {}).get("milestones", [])
                if str(item.get("skill", "")).strip().casefold()
                == str(m.external_key or "").strip().casefold()
            ),
            None,
        )
        try:
            proposals = evaluate(
                [{**serialize_milestone(m), "target_score": target}],
                snapshot,
                expected_scope=metadata.get("scope") or "public",
                expected_rubric=metadata.get("rubric") or VERSION,
                expected_period=metadata.get("period") or "all_time",
            )
        except IncomparableSnapshot as exc:
            raise HTTPException(409, "Roadmap suggestion context is stale") from exc
        if not proposals or proposals[0]["evidence"] != s.evidence:
            raise HTTPException(409, "Roadmap suggestion no longer meets criteria")
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
            if roadmap.data and isinstance(roadmap.data, dict):
                data = deepcopy(roadmap.data)
                for item in data.get("milestones", []):
                    if (
                        str(item.get("skill", "")).lower()
                        == str(m.external_key or "").lower()
                    ):
                        item["status"] = "completed"
                        item["verification_status"] = "verified"
                        item["evaluation_evidence"] = s.evidence
                        break
                roadmap.data = data
                flag_modified(roadmap, "data")
    s.state = decision
    s.resolved_at = datetime.now(UTC)
    db.commit()
    result = serialize_suggestion(s)
    if decision == "rejected" and s.snapshot_key != current_snapshot(db, user.id).key:
        result["evidence"] = []
    return result


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
