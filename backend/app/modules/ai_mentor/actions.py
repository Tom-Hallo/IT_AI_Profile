"""Create proposals and execute only server-stored, owner-confirmed actions."""

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.ai_mentor.action_models import MentorAction, MentorActionEvent
from app.modules.ai_mentor.action_schemas import (
    ActionDecision,
    ActionPreview,
    ActionResult,
    CVProposal,
    ReanalysisProposal,
    RoadmapProposal,
    tool_proposal_adapter,
)
from app.modules.analysis import service as analysis
from app.modules.analysis.router import dispatch
from app.modules.cvs.models import CV
from app.modules.roadmaps.models import Roadmap
from app.modules.users.models import User

logger = logging.getLogger(__name__)
TTL = timedelta(minutes=5)
IMPACTS = {
    "create_cv": "Lưu một bản nháp CV mới vào hồ sơ của bạn.",
    "create_roadmap": "Lưu một lộ trình học tập mới vào hồ sơ của bạn.",
    "reanalyze_repository": "Đưa repository vào hàng đợi phân tích của hệ thống.",
}


def _audit(db: Session, action: MentorAction, event: str) -> None:
    db.add(MentorActionEvent(action_id=action.id, event=event))


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
    elif uses_private_github:
        # Persisted CVs and roadmaps are reusable after GitHub consent is revoked.
        return None

    now = datetime.now(UTC)
    action = MentorAction(
        id=uuid4(),
        user_id=user.id,
        tool=proposal.tool,
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
        logger.error("Cannot store mentor proposal: %s", type(exc).__name__)
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
        else:
            model = CV if kind == "cv" else Roadmap
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
            else:
                assert isinstance(proposal, RoadmapProposal)
                draft = Roadmap(
                    user_id=user.id,
                    title=proposal.title,
                    data={"steps": proposal.steps},
                )
            db.add(draft)
            db.flush()
    except HTTPException:
        return _finish(db, action, "denied")
    except SQLAlchemyError as exc:
        logger.error("Mentor draft action failed: %s", type(exc).__name__)
        return _finish(db, action, "failed")
    return _finish(db, action, "succeeded", str(draft.id))
