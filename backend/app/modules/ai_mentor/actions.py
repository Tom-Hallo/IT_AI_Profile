"""Create proposals and execute only server-stored, owner-confirmed actions."""

import json
import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.modules.ai_audit.models import AIUsageEvent, Consent, Provider, Status, Tool
from app.modules.ai_mentor.action_models import MentorAction, MentorActionEvent
from app.modules.ai_mentor.action_schemas import (
    ActionDecision,
    ActionPreview,
    ActionResult,
    CVProposal,
    ReanalysisProposal,
    RoadmapProposal,
    UpdateRoadmapProposal,
    tool_proposal_adapter,
)
from app.modules.analysis import service as analysis
from app.modules.analysis.router import dispatch
from app.modules.cvs.models import CV
from app.modules.roadmap_tracking.models import Milestone, MilestoneHistory
from app.modules.roadmaps.models import Roadmap
from app.modules.users.models import User

logger = logging.getLogger(__name__)
TTL = timedelta(minutes=5)
IMPACTS = {
    "create_cv": "Lưu một bản nháp CV mới vào hồ sơ của bạn.",
    "create_roadmap": "Lưu một lộ trình học tập mới vào hồ sơ của bạn.",
    "update_roadmap": "Cập nhật các cột mốc trong lộ trình học tập đang mở của bạn.",
    "reanalyze_repository": "Đưa repository vào hàng đợi phân tích của hệ thống.",
}


def _audit(db: Session, action: MentorAction, event: str) -> None:
    db.add(MentorActionEvent(action_id=action.id, event=event))
    consent: Consent = (
        "declined"
        if event == "declined"
        else "not_requested"
        if event in {"proposed", "expired"}
        else "confirmed"
    )
    db.add(
        AIUsageEvent(
            user_id=action.user_id,
            operation_id=action.id,
            feature="mentor",
            phase="tool",
            source="chat",
            provider=action.audit_provider,
            consent=consent,
            status=cast(Status, event),
            tool=cast(Tool, action.tool),
        )
    )


def _finish(
    db: Session, action: MentorAction, status: str, result_id: str | None = None
) -> ActionResult:
    action.status = status
    action.result_id = result_id
    action.payload = None
    _audit(db, action, status)
    db.commit()
    return ActionResult(status=status, result_id=result_id)


def expire_pending_actions(db: Session) -> None:
    expired = db.scalars(
        select(MentorAction)
        .where(
            MentorAction.status == "pending",
            MentorAction.expires_at <= datetime.now(UTC),
        )
        .order_by(MentorAction.expires_at, MentorAction.id)
        .limit(100)
        .with_for_update(skip_locked=True)
    )
    for action in expired:
        action.status = "expired"
        action.payload = None
        _audit(db, action, "expired")


def propose_action(
    db: Session,
    user: User,
    model_text: str,
    *,
    selected_repos: list[int],
    context_refs: list[tuple[str, int]],
    sources: list[str],
    uses_private_github: bool,
    provider: Provider | None = None,
) -> ActionPreview | None:
    try:
        data = json.loads(model_text)
        proposal = tool_proposal_adapter.validate_python(data.get("proposal"))
    except (AttributeError, ValueError):
        return None

    scope = None
    if isinstance(proposal, ReanalysisProposal):
        repo_id = proposal.repository_id
        if repo_id not in selected_repos:
            return None
        try:
            repo = analysis.verify_repository_access(db, repo_id, user)
            analysis.require_access(db, user.id, repo_id)
        except HTTPException:
            return None
        scope = "private" if repo.private else "public"
        sources = [f"GitHub repository #{repo_id} ({scope})"]
        context_refs = []
    elif isinstance(proposal, UpdateRoadmapProposal):
        valid_roadmap = db.scalar(
            select(Roadmap.id).where(
                Roadmap.id == proposal.roadmap_id, Roadmap.user_id == user.id
            )
        )
        if valid_roadmap is None:
            # Never silently redirect an action to a different roadmap.
            return None
    elif uses_private_github:
        # Persisted CVs and roadmaps are reusable after GitHub consent is revoked.
        return None

    now = datetime.now(UTC)
    action = MentorAction(
        id=uuid4(),
        user_id=user.id,
        tool=proposal.tool,
        audit_provider=provider,
        status="pending",
        expires_at=now + TTL,
        payload={
            "proposal": proposal.model_dump(mode="json"),
            "refs": context_refs,
            "scope": scope,
        },
    )
    try:
        db.add(action)
        db.flush()
        _audit(db, action, "proposed")
        db.commit()
    except (SQLAlchemyError, UnicodeError) as exc:
        db.rollback()
        logger.error("Cannot store mentor proposal: %s: %s", type(exc).__name__, exc)
        raise HTTPException(503, "Unable to store mentor proposal") from None
    return ActionPreview(
        id=action.id,
        tool=proposal.tool,
        sources=sources,
        impact=IMPACTS[proposal.tool],
        proposal=proposal,
        expires_at=action.expires_at,
    )


def _check_draft_sources(db: Session, user: User, refs: list[tuple[str, int]]) -> None:
    for kind, id_ in refs:
        if kind == "github":
            if analysis.verify_repository_access(db, id_, user).private:
                raise HTTPException(403, "Repository visibility changed")
        elif kind == "roadmap":
            is_valid_roadmap = (
                db.scalar(
                    select(Roadmap.id).where(
                        Roadmap.id == id_, Roadmap.user_id == user.id
                    )
                )
                is not None
            )
            if not is_valid_roadmap:
                is_valid_milestone = (
                    db.scalar(
                        select(Milestone.id)
                        .join(Roadmap, Milestone.roadmap_id == Roadmap.id)
                        .where(Milestone.id == id_, Roadmap.user_id == user.id)
                    )
                    is not None
                )
                if not is_valid_milestone:
                    raise HTTPException(403, "Mentor source is no longer available")
        else:
            model = CV
            if (
                db.scalar(
                    select(model.id).where(model.id == id_, model.user_id == user.id)
                )
                is None
            ):
                raise HTTPException(403, "Mentor source is no longer available")


def decide_action(
    db: Session, user: User, action_id: UUID, decision: ActionDecision
) -> ActionResult:
    action = db.scalar(
        select(MentorAction)
        .where(MentorAction.id == action_id, MentorAction.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if action is None:
        raise HTTPException(404, "Mentor action not found")
    if action.status != "pending":
        result = ActionResult(status=action.status, result_id=action.result_id)
        db.rollback()  # Release the row lock even when the result is a replay.
        return result
    if action.expires_at <= datetime.now(UTC):
        return _finish(db, action, "expired")
    if decision.decision == "decline":
        return _finish(db, action, "declined")

    payload = action.payload or {}
    proposal = tool_proposal_adapter.validate_python(payload.get("proposal"))
    _audit(db, action, "confirmed")

    if isinstance(proposal, ReanalysisProposal):
        try:
            with db.begin_nested():
                repo = analysis.verify_repository_access(
                    db, proposal.repository_id, user
                )
                scope = payload["scope"]
                if repo.private != (scope == "private"):
                    raise HTTPException(403, "Repository visibility changed")
                job, created = analysis.create(
                    db, user.id, repo.id, scope, commit=False
                )
        except HTTPException as exc:
            denied = exc.status_code in (401, 403, 404)
            return _finish(db, action, "denied" if denied else "failed")
        except SQLAlchemyError as exc:
            logger.error("Mentor analysis action failed: %s", type(exc).__name__)
            return _finish(db, action, "failed")

        # The action, audit and job commit together. Existing maintenance
        # recovers a queued job if the process exits before Redis dispatch.
        result = _finish(db, action, "succeeded", str(job.id))
        if created or job.status == "queued":
            try:
                dispatch(job, db, recoverable=True)
            except HTTPException:
                _audit(db, action, "queue_deferred")
                db.commit()
        return result

    try:
        with db.begin_nested():
            _check_draft_sources(db, user, payload["refs"])
            if isinstance(proposal, CVProposal):
                draft = CV(
                    user_id=user.id,
                    content={
                        "title": proposal.title,
                        "summary": proposal.summary,
                        "skills": proposal.skills,
                    },
                )
                db.add(draft)
                db.flush()
                result_id = str(draft.id)
            elif isinstance(proposal, UpdateRoadmapProposal):
                roadmap = db.scalar(
                    select(Roadmap)
                    .where(
                        Roadmap.id == proposal.roadmap_id, Roadmap.user_id == user.id
                    )
                    .with_for_update()
                )
                if roadmap is None:
                    raise HTTPException(404, "Roadmap not found")
                if not isinstance(roadmap.data, dict):
                    raise HTTPException(409, "Roadmap data is not a valid object")
                data = deepcopy(roadmap.data)
                # Do not overwrite an unmigrated legacy steps-only roadmap.
                if data.get("steps") and "milestones" not in data:
                    raise HTTPException(
                        409, "Load roadmap tracking before extending legacy steps"
                    )
                milestones_data = data.get("milestones", [])
                if not isinstance(milestones_data, list) or any(
                    not isinstance(item, dict) for item in milestones_data
                ):
                    raise HTTPException(409, "Roadmap milestones are not a valid list")
                milestones_data = list(milestones_data)

                # JSONB array position is the canonical display order. Preserve
                # every existing milestone object (IDs, status, evidence, order).
                used_keys = {
                    str(item.get("skill", "")).strip().lower()
                    for item in milestones_data
                }
                used_keys.update(
                    str(key).strip().lower()
                    for key in db.scalars(
                        select(Milestone.external_key).where(
                            Milestone.roadmap_id == roadmap.id
                        )
                    ).all()
                )
                used_descriptions = {
                    str(item.get(field, "")).strip().casefold()
                    for item in milestones_data
                    for field in ("title", "objective")
                    if item.get(field)
                }
                next_order = max(
                    [len(milestones_data)]
                    + [
                        int(item["order"])
                        for item in milestones_data
                        if isinstance(item.get("order"), int)
                        and not isinstance(item["order"], bool)
                        and item["order"] >= 0
                    ]
                )

                def append_new(
                    skill: str, title: str, objective: str, metric: str, target: int
                ) -> None:
                    nonlocal next_order
                    skill_key = skill.strip().lower()
                    if not skill_key or len(skill_key) > 128 or skill_key in used_keys:
                        raise HTTPException(
                            409, "Milestone already exists or has an invalid skill"
                        )
                    used_keys.add(skill_key)
                    next_order += 1
                    milestones_data.append(
                        {
                            "skill": skill_key,
                            "title": title,
                            "target_score": target,
                            "current_score": None,
                            "gap": None,
                            "gap_type": "missing_evidence",
                            "priority": 2,
                            "objective": objective,
                            "metric": metric,
                            "evidence": [],
                            "confidence": "unknown",
                            "status": "todo",
                            "order": next_order,
                        }
                    )
                    db_m = Milestone(
                        roadmap_id=roadmap.id,
                        external_key=skill_key,
                        title=title,
                        required_skills=[skill_key],
                        status="pending",
                        version=1,
                    )
                    db.add(db_m)
                    db.flush()
                    db.add(
                        MilestoneHistory(
                            milestone_id=db_m.id,
                            actor_user_id=user.id,
                            old_status=None,
                            new_status="pending",
                            note=f"Added by AI Mentor: {title}",
                            source="mentor",
                        )
                    )

                for patch in (
                    [proposal.add_milestone] if proposal.add_milestone else []
                ) + proposal.add_milestones:
                    append_new(
                        patch.skill,
                        patch.title,
                        patch.objective,
                        patch.metric,
                        patch.target_score,
                    )
                    used_descriptions.update(
                        (
                            patch.title.strip().casefold(),
                            patch.objective.strip().casefold(),
                        )
                    )

                # Plain-text steps are appended as distinct milestones with
                # action-scoped keys. Never change existing skills to fit them.
                for idx, step in enumerate(proposal.steps, 1):
                    objective = step.strip()
                    if objective.casefold() in used_descriptions:
                        raise HTTPException(409, "Milestone step already exists")
                    used_descriptions.add(objective.casefold())
                    append_new(
                        f"mentor_{action.id.hex[:16]}_step_{idx}",
                        objective[:120],
                        objective,
                        f"Complete: {objective}"[:800],
                        75,
                    )

                # Handle modify_milestone
                if proposal.modify_milestone:
                    patch = proposal.modify_milestone
                    skill_key = patch.skill.lower().strip()
                    for m in milestones_data:
                        if skill_key in str(m.get("skill", "")).lower():
                            if patch.title:
                                m["title"] = patch.title
                            if patch.objective:
                                m["objective"] = patch.objective
                            if patch.metric:
                                m["metric"] = patch.metric
                            if patch.target_score:
                                m["target_score"] = patch.target_score
                    db_m = db.scalar(
                        select(Milestone).where(
                            Milestone.roadmap_id == roadmap.id,
                            Milestone.external_key == skill_key,
                        )
                    )
                    if db_m:
                        if patch.title:
                            db_m.title = patch.title
                        db_m.version += 1
                        db.add(
                            MilestoneHistory(
                                milestone_id=db_m.id,
                                actor_user_id=user.id,
                                old_status=db_m.status,
                                new_status=db_m.status,
                                note=f"Modified by AI Mentor: {patch.metric}",
                                source="mentor",
                            )
                        )

                data["milestones"] = milestones_data
                data["total"] = len(milestones_data)
                roadmap.data = data
                flag_modified(roadmap, "data")
                result_id = str(roadmap.id)
            else:
                assert isinstance(proposal, RoadmapProposal)
                milestones_list = [
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
                    for idx, step in enumerate(proposal.steps, 1)
                ]
                draft = Roadmap(
                    user_id=user.id,
                    title=proposal.title,
                    data={
                        "version": "pbi023-v1",
                        "goal": "backend",
                        "milestones": milestones_list,
                        "steps": proposal.steps,
                        "total": len(milestones_list),
                        "analysis_context": {
                            "scope": "public",
                            "rubric": "v2.1.0",
                            "period": "all_time",
                        },
                    },
                )
                db.add(draft)
                db.flush()
                for m in milestones_list:
                    db.add(
                        Milestone(
                            roadmap_id=draft.id,
                            external_key=m["skill"],
                            title=m["objective"][:100],
                            required_skills=[m["skill"]],
                        )
                    )
                result_id = str(draft.id)
    except HTTPException as exc:
        logger.warning(
            "Mentor draft action denied by HTTPException: %s (status %s)",
            exc.detail,
            exc.status_code,
        )
        return _finish(db, action, "denied")
    except SQLAlchemyError as exc:
        logger.error("Mentor draft action failed: %s", type(exc).__name__)
        return _finish(db, action, "failed")
    return _finish(db, action, "succeeded", result_id)
