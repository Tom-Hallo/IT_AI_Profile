"""PBI-022 coverage for action decisions on migrated PostgreSQL."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
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
from app.modules.career_roadmap.router import list_roadmaps
from app.modules.roadmap_tracking.models import Milestone
from app.modules.roadmap_tracking.router import get_tracking
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


def _seed_roadmap_with_progress(pg, owner):
    milestones = [
        {
            "skill": skill,
            "title": skill.title(),
            "objective": f"Learn {skill}",
            "order": index,
            "status": "completed" if index == 1 else "todo",
            "evidence": (
                [
                    {
                        "url": "https://github.com/test/repo/pull/1",
                        "verified": True,
                        "verification_status": "verified",
                    }
                ]
                if index == 1
                else []
            ),
        }
        for index, skill in enumerate(
            ("python", "fastapi", "postgresql", "testing", "docker", "deploy"), 1
        )
    ]
    roadmap = Roadmap(
        user_id=owner.id,
        title="Original learning path",
        data={"goal": "backend", "milestones": milestones, "total": 6},
    )
    pg.add(roadmap)
    pg.flush()
    for index, item in enumerate(milestones, 1):
        pg.add(
            Milestone(
                roadmap_id=roadmap.id,
                external_key=item["skill"],
                title=item["title"],
                required_skills=[item["skill"]],
                status="completed" if index == 1 else "pending",
                version=4 if index == 1 else 1,
            )
        )
    pg.commit()
    return roadmap


def test_mentor_append_two_milestones_preserves_original_progress_and_order(pg):
    owner = World(pg).user("append-owner@example.test")
    roadmap = _seed_roadmap_with_progress(pg, owner)
    before = deepcopy(roadmap.data)
    before_rows = {
        item.external_key: (item.id, item.status, item.version)
        for item in pg.scalars(
            select(Milestone).where(Milestone.roadmap_id == roadmap.id)
        )
    }
    proposal = propose(
        pg,
        owner,
        {
            "tool": "update_roadmap",
            "roadmap_id": roadmap.id,
            "title": "MUST NOT RENAME OLD ROADMAP",
            "add_milestones": [
                {
                    "skill": "system_design",
                    "title": "System Design",
                    "objective": "Build distributed systems",
                    "metric": "Architecture documented",
                    "after_skill": "python",
                },
                {
                    "skill": "microservices",
                    "title": "Microservices",
                    "objective": "Build services",
                    "metric": "Deploy services",
                },
            ],
        },
    )
    assert proposal is not None
    result = actions.decide_action(pg, owner, proposal.id, CONFIRM)
    assert result.status == "succeeded"
    assert result.result_id == str(roadmap.id)

    # Fresh DB session and tracking endpoint simulate a full-page reload.
    with Session(pg.bind, expire_on_commit=False) as fresh:
        stored = fresh.get(Roadmap, roadmap.id)
        assert stored.title == "Original learning path"
        assert stored.data["milestones"][:6] == before["milestones"]
        assert stored.data["total"] == 8
        assert [m["skill"] for m in stored.data["milestones"]][6:] == [
            "system_design",
            "microservices",
        ]
        assert [m["order"] for m in stored.data["milestones"]][6:] == [7, 8]
        tracking = get_tracking(roadmap.id, owner, fresh)
        assert [m["external_key"] for m in tracking["milestones"]] == [
            *[m["skill"] for m in before["milestones"]],
            "system_design",
            "microservices",
        ]
        assert [m["status"] for m in tracking["milestones"]] == [
            "completed",
            "pending",
            "pending",
            "pending",
            "pending",
            "pending",
            "pending",
            "pending",
        ]
        assert sum(m["status"] == "completed" for m in tracking["milestones"]) == 1
        after_rows = {
            m["external_key"]: (m["id"], m["status"], m["version"])
            for m in tracking["milestones"]
        }
        assert all(after_rows[key] == value for key, value in before_rows.items())
        assert (
            stored.data["milestones"][0]["evidence"]
            == before["milestones"][0]["evidence"]
        )


def test_mentor_independent_roadmap_created_at_end_of_list(pg):
    owner = World(pg).user("independent-roadmap@example.test")
    original = _seed_roadmap_with_progress(pg, owner)
    original_progress = deepcopy(original.data)
    proposal = propose(pg, owner, ROADMAP_DRAFT)
    assert proposal is not None
    result = actions.decide_action(pg, owner, proposal.id, CONFIRM)
    assert result.status == "succeeded"
    items = list_roadmaps(owner, pg)
    assert [item["id"] for item in items] == [
        original.id,
        int(result.result_id),
    ]
    pg.expire_all()
    assert pg.get(Roadmap, original.id).data == original_progress


def test_tracking_persisted_order_not_database_row_id(pg):
    owner = World(pg).user("reverse-tracking-order@example.test")
    original_order = ["python", "fastapi", "postgresql"]
    roadmap = Roadmap(
        user_id=owner.id,
        title="Reverse row insertion",
        data={
            "milestones": [
                {"skill": key, "order": idx, "evidence": []}
                for idx, key in enumerate(original_order, 1)
            ],
            "total": 3,
        },
    )
    pg.add(roadmap)
    pg.flush()
    # Simulate existing tracking rows inserted in an order different from JSONB.
    for key in reversed(original_order):
        pg.add(
            Milestone(
                roadmap_id=roadmap.id,
                external_key=key,
                title=key,
                required_skills=[key],
                status="completed" if key == "python" else "pending",
            )
        )
    pg.commit()

    with Session(pg.bind, expire_on_commit=False) as fresh:
        tracking = get_tracking(roadmap.id, owner, fresh)["milestones"]
        assert [m["external_key"] for m in tracking] == original_order
        assert tracking[0]["status"] == "completed"
        assert tracking[0]["id"] > tracking[-1]["id"]


def test_mentor_append_batch_duplicate_rolls_back_all_insertions(pg):
    owner = World(pg).user("batch-duplicate@example.test")
    roadmap = _seed_roadmap_with_progress(pg, owner)
    before = deepcopy(roadmap.data)
    action = propose(
        pg,
        owner,
        {
            "tool": "update_roadmap",
            "roadmap_id": roadmap.id,
            "add_milestones": [
                {
                    "skill": "advanced_backend",
                    "title": "Advanced Backend",
                    "objective": "Build backends",
                    "metric": "Service shipped",
                },
                {
                    "skill": "python",
                    "title": "Existing Python",
                    "objective": "Would overwrite original",
                    "metric": "Not allowed",
                },
            ],
        },
    )
    assert action is not None
    assert actions.decide_action(pg, owner, action.id, CONFIRM).status == "denied"
    pg.expire_all()
    assert pg.get(Roadmap, roadmap.id).data == before
    assert (
        pg.scalar(
            select(func.count())
            .select_from(Milestone)
            .where(Milestone.roadmap_id == roadmap.id)
        )
        == 6
    )


def test_mentor_append_uses_max_existing_order_without_renumbering(pg):
    owner = World(pg).user("max-position@example.test")
    roadmap = _seed_roadmap_with_progress(pg, owner)
    before = deepcopy(roadmap.data)
    before["milestones"][1]["order"] = 20
    roadmap.data = before
    pg.commit()
    proposal = propose(
        pg,
        owner,
        {
            "tool": "update_roadmap",
            "roadmap_id": roadmap.id,
            "steps": ["Tracing", "Performance"],
        },
    )
    assert proposal is not None
    assert actions.decide_action(pg, owner, proposal.id, CONFIRM).status == "succeeded"
    pg.expire_all()
    result = pg.get(Roadmap, roadmap.id).data
    assert result["milestones"][:6] == before["milestones"]
    assert [item["order"] for item in result["milestones"][-2:]] == [21, 22]


def test_mentor_steps_append_distinct_rows_and_do_not_renumber_existing(pg):
    owner = World(pg).user("steps-owner@example.test")
    roadmap = _seed_roadmap_with_progress(pg, owner)
    proposal = propose(
        pg,
        owner,
        {
            "tool": "update_roadmap",
            "roadmap_id": roadmap.id,
            "steps": ["Advanced architecture", "Distributed tracing"],
        },
    )
    assert actions.decide_action(pg, owner, proposal.id, CONFIRM).status == "succeeded"
    pg.expire_all()
    data = pg.get(Roadmap, roadmap.id).data
    assert [item["order"] for item in data["milestones"]] == list(range(1, 9))
    assert [item["objective"] for item in data["milestones"][-2:]] == [
        "Advanced architecture",
        "Distributed tracing",
    ]
    assert data["milestones"][0]["status"] == "completed"


def test_mentor_legacy_empty_milestones_cannot_hide_existing_steps(pg):
    owner = World(pg).user("legacy-steps-owner@example.test")
    data = {
        "goal": "backend",
        "steps": ["Complete Python fundamentals"],
        "milestones": [],
        "total": 1,
    }
    roadmap = Roadmap(user_id=owner.id, title="Legacy roadmap", data=data)
    pg.add(roadmap)
    pg.commit()

    action = propose(
        pg,
        owner,
        {
            "tool": "update_roadmap",
            "roadmap_id": roadmap.id,
            "steps": ["Add distributed system design"],
        },
    )
    assert action is not None
    assert actions.decide_action(pg, owner, action.id, CONFIRM).status == "denied"
    pg.expire_all()
    assert pg.get(Roadmap, roadmap.id).data == data
    assert (
        pg.scalar(
            select(func.count())
            .select_from(Milestone)
            .where(Milestone.roadmap_id == roadmap.id)
        )
        == 0
    )


def test_mentor_steps_append_rejects_existing_skill_name(pg):
    owner = World(pg).user("step-duplicate@example.test")
    roadmap = _seed_roadmap_with_progress(pg, owner)
    before = deepcopy(roadmap.data)
    action = propose(
        pg,
        owner,
        {
            "tool": "update_roadmap",
            "roadmap_id": roadmap.id,
            "steps": ["python"],
        },
    )
    assert action is not None
    assert actions.decide_action(pg, owner, action.id, CONFIRM).status == "denied"
    pg.expire_all()
    assert pg.get(Roadmap, roadmap.id).data == before
    assert (
        pg.scalar(
            select(func.count())
            .select_from(Milestone)
            .where(Milestone.roadmap_id == roadmap.id)
        )
        == 6
    )


def test_mentor_duplicate_skill_denies_without_modifying_evidence(pg):
    owner = World(pg).user("duplicate-owner@example.test")
    roadmap = _seed_roadmap_with_progress(pg, owner)
    snapshot = deepcopy(roadmap.data)
    before = pg.scalars(
        select(Milestone).where(Milestone.roadmap_id == roadmap.id)
    ).all()
    versions = [(m.id, m.status, m.version, m.title) for m in before]
    proposal = propose(
        pg,
        owner,
        {
            "tool": "update_roadmap",
            "roadmap_id": roadmap.id,
            "add_milestone": {
                "skill": "PYTHON",
                "title": "Overwrite forbidden",
                "objective": "Overwrite proof",
                "metric": "Invalid overwrite",
            },
        },
    )
    assert actions.decide_action(pg, owner, proposal.id, CONFIRM).status == "denied"
    pg.expire_all()
    assert pg.get(Roadmap, roadmap.id).data == snapshot
    assert [
        (m.id, m.status, m.version, m.title)
        for m in pg.scalars(select(Milestone).where(Milestone.roadmap_id == roadmap.id))
    ] == versions


def test_mentor_wrong_or_removed_roadmap_never_uses_latest(pg):
    owner = World(pg).user("target-owner@example.test")
    old_roadmap = _seed_roadmap_with_progress(pg, owner)
    newer_roadmap = Roadmap(
        user_id=owner.id,
        title="Newer unrelated roadmap",
        data={"milestones": [], "total": 0},
    )
    pg.add(newer_roadmap)
    pg.commit()
    draft = {
        "tool": "update_roadmap",
        "roadmap_id": old_roadmap.id + 123456,
        "steps": ["Must not land on newer roadmap"],
    }
    assert propose(pg, owner, draft) is None
    draft["roadmap_id"] = old_roadmap.id
    action = propose(pg, owner, draft)
    assert action is not None
    pg.delete(old_roadmap)
    pg.commit()
    assert actions.decide_action(pg, owner, action.id, CONFIRM).status == "denied"
    pg.expire_all()
    assert pg.get(Roadmap, newer_roadmap.id).data == {"milestones": [], "total": 0}
