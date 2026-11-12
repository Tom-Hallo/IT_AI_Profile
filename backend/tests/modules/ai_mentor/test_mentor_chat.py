"""PBI-021 egress tests exercise the real provider adapter and database guards."""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.providers import openai_provider
from app.core.config import settings
from app.modules.ai_mentor import service
from app.modules.ai_mentor.schemas import MentorChatRequest
from app.modules.consent.models import PrivateConsent
from app.modules.consent.service import ACCESS, EXTERNAL, POLICY_VERSION
from app.modules.cvs.models import CV
from app.modules.roadmaps.models import Roadmap
from tests.modules.role_scoring import conftest as fixtures
from tests.modules.role_scoring.conftest import (
    SECRET_CONTENT,
    SECRET_RATIONALE,
    World,
)

CHAT = "/api/v1/mentor/chat"
SOURCES = "/api/v1/mentor/sources"
ALLOWED = "backend/app/main.py"
UNAPPROVED = "backend/app/unapproved.py"


db = fixtures.db
make_client = fixtures.make_client


@pytest.fixture
def transport(monkeypatch):
    requests = []
    response = Mock()
    response.side_effect = lambda _: httpx.Response(
        200,
        json={
            "output_text": json.dumps(
                {
                    "claims": [
                        {"text": "Có bằng chứng phù hợp.", "evidence_ids": ["E1"]}
                    ],
                    "limitations": ["Hai nguồn cung cấp thông tin khác nhau."],
                }
            )
        },
    )
    real_client = httpx.AsyncClient

    def handle(request):
        body = json.loads(request.content)
        assert body["store"] is False
        requests.append(json.loads(json.loads(body["input"].split("\n", 1)[1])))
        return response(request)

    monkeypatch.setattr(
        openai_provider.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setattr(service, "count_ai_requests_today", Mock(return_value=0))
    monkeypatch.setattr(service, "record_ai_usage", Mock())
    config = settings.model_copy(
        update={
            "ai_provider": "openai",
            "ai_model": "test-model",
            "ai_api_key": SecretStr("local-test-placeholder"),
        }
    )
    monkeypatch.setattr(
        service,
        "get_ai_provider",
        lambda _: openai_provider.OpenAIProvider(config),
    )
    return requests, response, config


def chat(db, user, transport, **sources):
    return asyncio.run(
        service.run_mentor_chat(
            db=db,
            user=user,
            config=transport[2],
            payload=MentorChatRequest(message="Tư vấn giúp tôi", sources=sources),
        )
    )


def grant(db, user, repo, *, external=True):
    for id_, kind, provider, paths in (
        (1, ACCESS, "", [ALLOWED, UNAPPROVED]),
        (2, EXTERNAL, "openai", [ALLOWED, "backend/app/external_only.py"]),
    ):
        if id_ == 2 and not external:
            continue
        db.add(
            PrivateConsent(
                id=id_,
                user_id=user.id,
                repository_id=repo.id,
                consent_type=kind,
                provider_key=provider,
                policy_version=POLICY_VERSION,
                scope=paths,
                granted=True,
                granted_at=datetime.now(UTC),
            )
        )
    db.commit()


def private_world(db):
    world = World(db)
    user = world.user("owner@example.test", private_enabled=True)
    repo = world.repo(user, private=True)
    repo.full_name = "company/private-repository"
    world.report(
        repo,
        [
            ("api_service", ALLOWED, "source_code"),
            ("unapproved_classification", UNAPPROVED, "source_code"),
        ],
    )
    return user, repo


def assert_private_scope(db, transport):
    user, repo = private_world(db)
    grant(db, user, repo)
    reply = chat(db, user, transport, github_repo_ids=[repo.id])
    assert reply.sources_used == ["github"]
    assert reply.evidence[0].id == "E1"
    assert "[E1]" in reply.answer
    assert reply.confidence is None
    assert transport[0][0]["sources"] == [
        {
            "id": "E1",
            "source": "github",
            "data": {
                "path": ALLOWED,
                "classification": "api_service",
                "finding_type": "architecture",
            },
        }
    ]
    payload = json.dumps(transport[0])
    for secret in (SECRET_CONTENT, SECRET_RATIONALE, UNAPPROVED, repo.full_name):
        assert secret not in payload
    assert service.record_ai_usage.call_args.kwargs["repository_id"] is None


def test_private_payload_matches_intersection(db, transport):
    assert_private_scope(db, transport)


def test_private_payload_on_migrated_postgres(
    temp_database_url, alembic_cli, transport
):
    migrated = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert migrated.returncode == 0, migrated.stderr
    engine = create_engine(temp_database_url)
    try:
        with Session(engine) as session:
            assert_private_scope(session, transport)
    finally:
        engine.dispose()


def test_private_local_consent_does_not_authorize_external_ai(db, transport):
    user, repo = private_world(db)
    grant(db, user, repo, external=False)
    result = chat(db, user, transport, github_repo_ids=[repo.id])
    assert [item.code for item in result.limitations] == ["github_denied"]
    assert result.sources_used == []
    assert transport[0] == []


def test_revocation_stops_retry_before_second_provider_request(db, transport):
    user, repo = private_world(db)
    grant(db, user, repo)

    def revoke_during_first_request(_):
        db.get(PrivateConsent, 2).revoked_at = datetime.now(UTC)
        db.commit()
        return httpx.Response(500)

    transport[1].side_effect = revoke_during_first_request
    result = chat(db, user, transport, github_repo_ids=[repo.id])
    assert len(transport[0]) == 1
    assert result.evidence == []
    assert [item.code for item in result.limitations] == ["consent_changed"]
    assert service.record_ai_usage.call_args.kwargs["status"] == "consent_changed"


def test_account_and_selection_isolation_at_api_and_provider(
    db, make_client, transport
):
    world = World(db)
    user = world.user("alice@example.test")
    outsider = world.user("bob@example.test")
    foreign_repo = world.repo(outsider)
    db.add_all(
        [
            CV(id=1, user_id=user.id, content={"skills": ["SELECTED_CV"]}),
            CV(id=2, user_id=user.id, content={"skills": ["UNSELECTED_CV"]}),
            CV(id=3, user_id=outsider.id, content={"skills": ["FOREIGN_CV"]}),
            Roadmap(
                id=1, user_id=user.id, title="Selected", data={"step": "OWN_ROADMAP"}
            ),
            Roadmap(id=2, user_id=outsider.id, title="FOREIGN_ROADMAP", data={}),
        ]
    )
    db.commit()
    client = make_client(user)
    options = client.get(SOURCES)
    assert options.status_code == 200
    assert options.headers["cache-control"] == "no-store"
    assert {item["id"] for item in options.json()["cvs"]} == {1, 2}
    assert options.json()["roadmaps"] == [{"id": 1, "title": "Selected"}]
    result = client.post(
        CHAT,
        headers={"Origin": settings.frontend_url},
        json={
            "message": "So sánh các nguồn",
            "sources": {
                "github_repo_ids": [foreign_repo.id],
                "cv_ids": [1, 3],
                "roadmap_ids": [1, 2],
                "jd_text": "SELECTED_JD",
            },
        },
    )
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["sources_used"] == ["cv", "jd", "roadmap"]
    assert {item["code"] for item in result.json()["limitations"]} == {
        "github_denied",
        "cv_unavailable",
        "roadmap_unavailable",
        "model_limitation",
        "confidence_unavailable",
    }
    context = transport[0][0]
    assert [item["source"] for item in context["sources"]] == ["cv", "jd", "roadmap"]
    for value in ("UNSELECTED_CV", "FOREIGN_CV", "FOREIGN_ROADMAP", foreign_repo.name):
        assert value not in json.dumps(context)
    for value in ("SELECTED_CV", "SELECTED_JD", "OWN_ROADMAP"):
        assert value in json.dumps(context)


def test_auth_origin_and_invalid_ids(make_client, db, transport):
    user = World(db).user("auth@example.test")
    payload = {"message": "Test", "sources": {"jd_text": "test"}}
    headers = {"Origin": settings.frontend_url}
    assert make_client().get(SOURCES).status_code == 401
    assert make_client().post(CHAT, json=payload, headers=headers).status_code == 401
    client = make_client(user)
    assert client.post(CHAT, json=payload).status_code == 403
    assert (
        client.post(
            CHAT, json=payload, headers={"Origin": "https://other.test"}
        ).status_code
        == 403
    )
    payload["sources"]["github_repo_ids"] = [2**63]
    assert client.post(CHAT, json=payload, headers=headers).status_code == 422
    assert transport[0] == []


def test_budget_skips_complete_chunks_and_unknown_citations_are_rejected(db, transport):
    user = World(db).user("budget@example.test")
    db.add(CV(id=1, user_id=user.id, content={"large": "x" * 800}))
    db.commit()
    transport[2].ai_max_input_chars = 175
    transport[1].side_effect = lambda _: httpx.Response(
        200,
        json={
            "output_text": json.dumps(
                {
                    "claims": [{"text": "Unsupported claim", "evidence_ids": ["E999"]}],
                    "limitations": [],
                }
            )
        },
    )
    result = chat(db, user, transport, cv_ids=[1], jd_text="Short JD")
    assert result.sources_used == ["jd"]
    assert result.evidence == []
    assert [item.code for item in result.limitations] == [
        "input_budget",
        "invalid_answer",
    ]
    assert "Unsupported claim" not in result.answer
    assert len(transport[0]) == 1
    assert transport[0][0]["sources"] == [
        {"id": "E1", "source": "jd", "data": {"text": "Short JD"}}
    ]


def test_empty_selection_and_empty_owned_cv_do_not_call_provider(db, transport):
    user = World(db).user("empty@example.test")
    db.add(CV(id=1, user_id=user.id, content={}))
    db.commit()
    assert chat(db, user, transport).limitations[0].code == "no_sources"
    assert chat(db, user, transport, cv_ids=[1]).limitations[0].code == "cv_unavailable"
    assert transport[0] == []
