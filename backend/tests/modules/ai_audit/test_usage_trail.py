"""PBI-038 integration coverage on migrated, isolated PostgreSQL."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.modules.ai_audit.models import AIUsageEvent
from app.modules.ai_mentor import actions
from app.modules.consent.models import PrivateConsent
from app.modules.cvs.models import CV
from tests.modules.ai_mentor import test_agent_actions as tools
from tests.modules.ai_mentor import test_mentor_chat as mentor
from tests.modules.role_scoring import conftest as fixtures

db = tools.pg
make_client = fixtures.make_client
transport = mentor.transport

AUDIT = "/api/v1/ai-audit"
PRIVATE_CV = "Private CV contents must stay outside audit"
PRIVATE_PATH = "owner-only private path"


def rows(db, user_id):
    return db.scalars(
        select(AIUsageEvent)
        .where(AIUsageEvent.user_id == user_id)
        .order_by(AIUsageEvent.id)
    ).all()


def test_consent_denial_and_success_reveal_only_metadata(db, make_client, transport):
    user, repo = mentor.private_world(db)
    user_id = user.id
    repo.full_name = PRIVATE_PATH
    db.commit()
    mentor.grant(db, user, repo, external=False)
    denied = mentor.chat(db, user, transport, github_repo_ids=[repo.id])
    assert denied.sources_used == []
    assert not transport[0]
    first = rows(db, user_id)
    assert [(row.phase, row.source, row.consent, row.status) for row in first] == [
        ("context", "github", "denied", "denied"),
    ]

    db.execute(text("DELETE FROM ita.private_consents"))
    db.commit()
    mentor.grant(db, user, repo)
    cv = CV(user_id=user_id, content={"text": PRIVATE_CV})
    db.add(cv)
    db.commit()
    reply = mentor.chat(db, user, transport, github_repo_ids=[repo.id], cv_ids=[cv.id])
    assert reply.sources_used == ["github", "cv"]
    assert len(transport[0]) == 1
    assert len(rows(db, user_id)) == 9

    audit = make_client(user).get(AUDIT)
    assert audit.status_code == 200, audit.text
    assert audit.headers["cache-control"] == "no-store"
    for marker in (PRIVATE_CV, PRIVATE_PATH, mentor.ALLOWED, "Tư vấn", "repository_id"):
        assert marker not in audit.text
    accepted = audit.json()["items"][:-1]
    assert len({item["operation_id"] for item in accepted}) == 1
    assert {item["provider"] for item in accepted} == {"openai"}
    assert {
        (item["phase"], item["source"], item["consent"], item["status"])
        for item in accepted
    } == {
        ("context", "github_private", "double_granted", "retrieved"),
        ("context", "cv", "selected", "retrieved"),
        ("provider", "github_private", "double_granted", "started"),
        ("provider", "cv", "selected", "started"),
        ("provider", "chat", "selected", "started"),
        ("provider", "github_private", "double_granted", "succeeded"),
        ("provider", "cv", "selected", "succeeded"),
        ("provider", "chat", "selected", "succeeded"),
    }
    timestamps = [datetime.fromisoformat(item["created_at"]) for item in accepted]
    assert all(timestamp.utcoffset() is not None for timestamp in timestamps)


def test_revocation_blocks_retry_and_records_denial(db, transport):
    user, repo = mentor.private_world(db)
    user_id = user.id
    mentor.grant(db, user, repo)

    def revoke(_):
        db.get(PrivateConsent, 2).revoked_at = datetime.now(UTC)
        db.commit()
        return httpx.Response(500)

    transport[1].side_effect = revoke
    reply = mentor.chat(db, user, transport, github_repo_ids=[repo.id])
    assert not reply.evidence
    assert len(transport[0]) == 1
    provider = [item for item in rows(db, user_id) if item.phase == "provider"]
    assert [item.status for item in provider] == ["started", "started", "denied"]
    assert provider[-1].consent == "denied"


def test_audit_write_failure_blocks_outbound_ai(db, transport):
    owner = fixtures.World(db).user("audit-fail@example.test")

    def refuse_started(session, _flush_context, _instances):
        if any(
            isinstance(obj, AIUsageEvent) and obj.status == "started"
            for obj in session.new
        ):
            raise SQLAlchemyError(
                "Do not include this exception detail in the response"
            )

    engine_session = type(db)
    event.listen(engine_session, "before_flush", refuse_started)
    try:
        with pytest.raises(HTTPException) as exc:
            mentor.chat(db, owner, transport, jd_text="Backend job")
    finally:
        event.remove(engine_session, "before_flush", refuse_started)
    assert exc.value.status_code == 503
    assert "exception detail" not in exc.value.detail
    assert transport[0] == []
    assert all(row.status != "started" for row in rows(db, owner.id))


def test_tool_outcome_failure_and_owner_isolation(db, make_client, monkeypatch):
    world = fixtures.World(db)
    owner = world.user("audit-owner@example.test")
    other = world.user("audit-other@example.test")
    repo = world.repo(owner)
    owner_id = owner.id
    created = tools.propose(db, owner, tools.CV_DRAFT, provider="ollama")
    assert (
        actions.decide_action(db, owner, created.id, tools.CONFIRM).status
        == "succeeded"
    )
    assert (
        actions.decide_action(db, owner, created.id, tools.CONFIRM).status
        == "succeeded"
    )
    monkeypatch.setattr(
        actions.analysis, "get_user_github_token", lambda *_: ("test", "read:user")
    )
    failed = tools.propose(
        db,
        owner,
        {"tool": "reanalyze_repository", "repository_id": repo.id},
        selected_repos=[repo.id],
        provider="openai",
    )

    def fail(*_args, **_kwargs):
        raise HTTPException(503, "Private tool payload must not appear")

    monkeypatch.setattr(actions.analysis, "create", fail)
    assert actions.decide_action(db, owner, failed.id, tools.CONFIRM).status == "failed"
    assert [(row.tool, row.provider, row.status) for row in rows(db, owner_id)] == [
        ("create_cv", "ollama", "proposed"),
        ("create_cv", "ollama", "confirmed"),
        ("create_cv", "ollama", "succeeded"),
        ("reanalyze_repository", "openai", "proposed"),
        ("reanalyze_repository", "openai", "confirmed"),
        ("reanalyze_repository", "openai", "failed"),
    ]

    assert make_client().get(AUDIT).status_code == 401
    assert make_client(other).get(AUDIT, params={"user_id": owner_id}).json() == {
        "items": [],
        "next_before": None,
    }
    client = make_client(owner)
    one = client.get(AUDIT, params={"limit": 3}).json()
    assert one["next_before"] == one["items"][-1]["id"]
    two = client.get(AUDIT, params={"limit": 3, "before": one["next_before"]}).json()
    assert two["next_before"] is None
    entries = one["items"] + two["items"]
    assert len({entry["id"] for entry in entries}) == 6
    assert {UUID(entry["operation_id"]) for entry in entries} == {created.id, failed.id}
    assert all(
        "payload" not in entry and "repository_id" not in entry for entry in entries
    )
    assert "Private tool" not in str(entries)
    assert tools.CV_DRAFT["summary"] not in str(entries)


def test_db_rejects_out_of_policy_audit_value(db):
    user = fixtures.World(db).user("audit-constraint@example.test")
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO ita.ai_usage_events "
                "(user_id, operation_id, feature, phase, source, consent, status) "
                "VALUES (:id, :op, 'mentor', 'tool', 'user supplied payload', "
                "'confirmed', 'started')"
            ),
            {"id": user.id, "op": uuid4()},
        )
    db.rollback()


def test_gateway_uses_same_audit_contract(db, transport, monkeypatch):
    import asyncio

    from app.modules.ai_mentor import policy_gateway

    owner, repo = mentor.private_world(db)
    repo_id, user_id = repo.id, owner.id
    mentor.grant(db, owner, repo)
    monkeypatch.setattr(policy_gateway, "count_ai_requests_today", lambda **_: 0)
    monkeypatch.setattr(policy_gateway, "record_ai_usage", lambda **_: None)
    result = asyncio.run(
        policy_gateway.generate_with_policy(
            db=db,
            user_id=user_id,
            repo_id=repo_id,
            files={mentor.ALLOWED: "Confidential source body"},
            instructions="Analyze the file",
            config=transport[2],
        )
    )
    assert result
    assert [
        (row.feature, row.source, row.consent, row.status) for row in rows(db, user_id)
    ] == [
        ("repository_ai", "github", "policy_allowed", "retrieved"),
        ("repository_ai", "github", "policy_allowed", "started"),
        ("repository_ai", "github", "policy_allowed", "succeeded"),
    ]


def test_consent_revoked_during_audit_commit_is_rechecked(db, transport, monkeypatch):
    from sqlalchemy.orm import Session

    from app.modules.ai_audit.service import Trace

    user, repo = mentor.private_world(db)
    user_id = user.id
    mentor.grant(db, user, repo)
    bind = db.get_bind()
    actual_write = Trace.write

    def write_then_revoke(self, db, phase, sources, status, **kwargs):
        actual_write(self, db, phase, sources, status, **kwargs)
        if status == "started":
            with Session(bind) as other, other.begin():
                other.get(PrivateConsent, 2).revoked_at = datetime.now(UTC)

    monkeypatch.setattr(Trace, "write", write_then_revoke)
    reply = mentor.chat(db, user, transport, github_repo_ids=[repo.id])
    assert not reply.sources_used
    assert not transport[0]
    assert rows(db, user_id)[-1].status == "denied"
