"""PBI-022 coverage for action decisions on migrated PostgreSQL."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.main import create_app
from app.modules.ai_mentor import actions, service
from app.modules.ai_mentor.action_models import MentorAction, MentorActionEvent
from app.modules.ai_mentor.action_schemas import ActionDecision, tool_proposal_adapter
from app.modules.ai_mentor.schemas import MentorChatRequest
from app.modules.analysis import router as analysis_router
from app.modules.analysis.models import AnalysisJob
from app.modules.consent.models import PrivateConsent
from app.modules.cvs.models import CV
from app.modules.roadmaps.models import Roadmap
from app.modules.users.models import User
from app.workers.enqueue import fetch_job
from tests.modules.role_scoring.conftest import World

CV_DRAFT = {
    "tool": "create_cv",
    "title": "Backend draft",
    "summary": "Candidate notes from this request.",
    "skills": ["Python"],
}
ROADMAP_DRAFT = {
    "tool": "create_roadmap",
    "title": "Backend",
    "steps": ["Practice SQL"],
}
CONFIRM = ActionDecision(decision="confirm")
DECLINE = ActionDecision(decision="decline")


@pytest.fixture
def pg(temp_database_url, alembic_cli):
    result = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert result.returncode == 0, result.stderr
    engine = create_engine(temp_database_url)
    try:
        with Session(engine, expire_on_commit=False) as db:
            yield db
    finally:
        engine.dispose()


def propose(db, owner, draft, **kwargs):
    defaults = dict(
        selected_repos=[], context_refs=[], sources=["Chat"], uses_private_github=False
    )
    return actions.propose_action(
        db, owner, json.dumps({"proposal": draft}), **(defaults | kwargs)
    )


def events(db, action_id):
    return db.scalars(
        select(MentorActionEvent.event)
        .where(MentorActionEvent.action_id == action_id)
        .order_by(MentorActionEvent.id)
    ).all()


@pytest.mark.parametrize(
    "payload",
    [
        {"tool": "delete_repository"},
        {"tool": "reanalyze_repository", "repository_id": True},
        {"tool": "reanalyze_repository", "repository_id": "123"},
        {"tool": "reanalyze_repository", "repository_id": 0},
        {**CV_DRAFT, "user_id": 99},
        {**CV_DRAFT, "summary": " "},
        {**ROADMAP_DRAFT, "steps": []},
    ],
)
def test_allowlist_rejects_invalid_arguments(payload):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        tool_proposal_adapter.validate_python(payload)


def test_chat_proposes_then_concurrent_confirm_only_creates_one_cv(pg, monkeypatch):
    owner = World(pg).user("owner@example.test")
    user_id = owner.id
    generated = AsyncMock(
        return_value={
            "text": json.dumps({"claims": [], "limitations": [], "proposal": CV_DRAFT})
        }
    )
    monkeypatch.setattr(
        service, "get_ai_provider", lambda _: SimpleNamespace(generate=generated)
    )
    monkeypatch.setattr(service, "count_ai_requests_today", lambda **_: 0)
    response = asyncio.run(
        service.run_mentor_chat(
            db=pg,
            user=owner,
            payload=MentorChatRequest(message="Tạo một CV Python", enable_actions=True),
        )
    )
    assert response.action is not None
    action_id = response.action.id
    assert pg.scalar(select(func.count()).select_from(CV)) == 0
    assert events(pg, action_id) == ["proposed"]

    def confirm():
        with Session(pg.bind, expire_on_commit=False) as session:
            return actions.decide_action(
                session, session.get(User, user_id), action_id, CONFIRM
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: confirm(), range(2)))
    assert first == second
    assert first.status == "succeeded"
    draft = pg.scalars(select(CV)).one()
    assert draft.user_id == user_id
    assert draft.content["summary"] == CV_DRAFT["summary"]
    assert first.result_id == str(draft.id)
    pg.expire_all()
    assert pg.get(MentorAction, action_id).payload is None
    assert events(pg, action_id) == ["proposed", "confirmed", "succeeded"]


def test_decision_api_requires_owner_origin_and_valid_input(pg):
    world = World(pg)
    owner = world.user("owner@example.test")
    other = world.user("other@example.test")
    proposal = propose(pg, owner, ROADMAP_DRAFT)
    assert proposal is not None
    path = f"/api/v1/agent/actions/{proposal.id}/approve"
    headers = {"Origin": settings.frontend_url}
    app = create_app()
    app.dependency_overrides[get_session] = lambda: pg
    client = TestClient(app)
    assert (
        client.post(path, headers=headers, json={"decision": "confirm"}).status_code
        == 401
    )
    app.dependency_overrides[get_current_user] = lambda: other
    assert (
        client.post(path, headers=headers, json={"decision": "confirm"}).status_code
        == 404
    )
    app.dependency_overrides[get_current_user] = lambda: owner
    assert client.post(path, json={"decision": "confirm"}).status_code == 403
    invalid = path.replace("/approve", "/delete")
    assert client.post(invalid, headers=headers).status_code == 422
    accepted = client.post(path, headers=headers, json={"title": "tampered"})
    assert accepted.status_code == 200
    assert accepted.headers["Cache-Control"] == "no-store"
    assert accepted.json()["status"] == "succeeded"
    roadmap = pg.scalars(select(Roadmap)).one()
    assert (
        roadmap.user_id == owner.id and roadmap.data["steps"] == ROADMAP_DRAFT["steps"]
    )


def test_declined_and_expired_proposals_never_execute(pg):
    owner = World(pg).user("owner@example.test")
    declined = propose(pg, owner, ROADMAP_DRAFT)
    expired = propose(pg, owner, ROADMAP_DRAFT)
    assert actions.decide_action(pg, owner, declined.id, DECLINE).status == "declined"
    assert actions.decide_action(pg, owner, declined.id, CONFIRM).status == "declined"
    pg.get(MentorAction, expired.id).expires_at = datetime.now(UTC) - timedelta(
        seconds=1
    )
    pg.commit()
    assert actions.decide_action(pg, owner, expired.id, CONFIRM).status == "expired"
    assert events(pg, declined.id) == ["proposed", "declined"]
    assert events(pg, expired.id) == ["proposed", "expired"]
    assert pg.scalar(select(func.count()).select_from(Roadmap)) == 0


def test_reanalysis_checks_current_consent_and_deduplicates(pg, monkeypatch):
    world = World(pg)
    owner = world.user("owner@example.test", private_enabled=True)
    private = world.repo(owner, private=True)
    public = world.repo(owner)
    world.consent(owner, private)
    monkeypatch.setattr(
        actions.analysis, "get_user_github_token", lambda *_: ("test", "repo")
    )
    dispatch = Mock()
    monkeypatch.setattr(actions, "dispatch", dispatch)

    def reanalysis(repo):
        return propose(
            pg,
            owner,
            {"tool": "reanalyze_repository", "repository_id": repo.id},
            selected_repos=[repo.id],
        )

    private_action = reanalysis(private)
    assert private_action is not None
    assert pg.scalar(select(func.count()).select_from(AnalysisJob)) == 0
    pg.scalars(select(PrivateConsent)).one().revoked_at = datetime.now(UTC)
    pg.commit()
    assert (
        actions.decide_action(pg, owner, private_action.id, CONFIRM).status == "denied"
    )
    assert events(pg, private_action.id) == ["proposed", "confirmed", "denied"]
    dispatch.assert_not_called()

    public_action = reanalysis(public)
    result = actions.decide_action(pg, owner, public_action.id, CONFIRM)
    assert result.status == "succeeded"
    assert result == actions.decide_action(pg, owner, public_action.id, CONFIRM)
    job = pg.scalars(select(AnalysisJob)).one()
    assert (job.user_id, job.repo_id, job.scope) == (owner.id, public.id, "public")
    assert result.result_id == str(job.id)
    dispatch.assert_called_once()


def test_deleted_sources_and_private_draft_are_blocked(pg):
    owner = World(pg).user("owner@example.test")
    cv = CV(user_id=owner.id, content={"summary": "test"})
    pg.add(cv)
    pg.commit()
    action = propose(pg, owner, CV_DRAFT, context_refs=[("cv", cv.id)])
    pg.delete(cv)
    pg.commit()
    assert actions.decide_action(pg, owner, action.id, CONFIRM).status == "denied"
    assert propose(pg, owner, CV_DRAFT, uses_private_github=True) is None
    with pytest.raises(HTTPException) as error:
        actions.decide_action(pg, owner, uuid4(), CONFIRM)
    assert error.value.status_code == 404
    assert pg.scalar(select(func.count()).select_from(CV)) == 0


def test_maintenance_clears_expired_draft_payload(pg):
    owner = World(pg).user("owner@example.test")
    action = propose(pg, owner, CV_DRAFT)
    pg.get(MentorAction, action.id).expires_at = datetime.now(UTC) - timedelta(
        seconds=1
    )
    pg.commit()
    actions.expire_pending_actions(pg)
    pg.commit()
    assert pg.get(MentorAction, action.id).payload is None
    assert events(pg, action.id) == ["proposed", "expired"]


def test_confirm_dispatches_real_rq_job(pg, monkeypatch):
    world = World(pg)
    owner = world.user("owner@example.test")
    repo = world.repo(owner)
    monkeypatch.setattr(
        actions.analysis, "get_user_github_token", lambda *_: ("test", "read:user")
    )
    action = propose(
        pg,
        owner,
        {"tool": "reanalyze_repository", "repository_id": repo.id},
        selected_repos=[repo.id],
    )
    result = actions.decide_action(pg, owner, action.id, CONFIRM)
    assert result.status == "succeeded"
    job = fetch_job(f"analysis-{result.result_id}")
    try:
        assert job.func_name == "app.workers.tasks.analysis.run_analysis"
        assert list(job.args) == [result.result_id]
        assert actions.decide_action(pg, owner, action.id, CONFIRM) == result
        assert events(pg, action.id) == ["proposed", "confirmed", "succeeded"]
    finally:
        job.delete(remove_from_queue=True)


def test_redis_outage_preserves_one_job_for_maintenance(pg, monkeypatch):
    world = World(pg)
    owner = world.user("owner@example.test")
    repo = world.repo(owner)
    monkeypatch.setattr(
        actions.analysis, "get_user_github_token", lambda *_: ("test", "read:user")
    )
    queue = Mock(side_effect=RedisConnectionError("test queue unavailable"))
    monkeypatch.setattr(analysis_router, "enqueue_task", queue)
    action = propose(
        pg,
        owner,
        {"tool": "reanalyze_repository", "repository_id": repo.id},
        selected_repos=[repo.id],
    )

    result = actions.decide_action(pg, owner, action.id, CONFIRM)
    assert result.status == "succeeded"
    assert result == actions.decide_action(pg, owner, action.id, CONFIRM)
    job = pg.scalars(select(AnalysisJob)).one()
    assert job.status == "queued"
    assert str(job.id) == result.result_id
    assert events(pg, action.id) == [
        "proposed",
        "confirmed",
        "succeeded",
        "queue_deferred",
    ]
    queue.assert_called_once()
