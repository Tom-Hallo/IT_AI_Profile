"""PBI-017 trên PostgreSQL thật (schema dựng bằng Alembic ``upgrade head``).

Cần ``RUN_INTEGRATION=1`` và PostgreSQL; dùng DB tạm riêng, xóa sau khi chạy.
Nguồn skill PBI-016 vẫn là ``StubSource`` vì PBI-016 chưa có trong source.
"""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.modules.role_scoring.conftest import (
    SECRET_CONTENT,
    SECRET_RATIONALE,
    StubSource,
)
from tests.modules.role_scoring.test_api import API, score

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="cần RUN_INTEGRATION=1 và PostgreSQL đang chạy",
)

LAYERED = ("layered_architecture", "backend/app/services/s.py", "source_code")
EVIDENCE = [API, LAYERED]


@pytest.fixture
def db(temp_database_url, alembic_cli):
    result = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert result.returncode == 0, result.stderr[-2000:]
    engine = create_engine(temp_database_url)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _body(client):
    resp = score(client, role="backend_developer")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_verified_public_repo_is_scored_without_leaking_private_fields(
    world, make_client
):
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, EVIDENCE)
    client = make_client(user, StubSource(None))

    resp = score(client, role="backend_developer")
    body = resp.json()

    statuses = {c["key"]: c["status"] for c in body["criteria"]}
    assert statuses["api_service_design"] == "SCORED"
    assert statuses["layered_structure"] == "SCORED"
    raw = json.dumps(body)
    assert SECRET_CONTENT not in raw
    assert SECRET_RATIONALE not in raw
    assert "matched_content" not in raw


def test_private_repo_without_consent_is_forbidden(world, make_client):
    user = world.user("dev@x.dev", private_enabled=True)
    repo = world.repo(user, private=True)
    world.report(repo, EVIDENCE)
    client = make_client(user, StubSource(None))

    resp = score(client, role="backend_developer", repository_id=repo.id)

    assert resp.status_code == 403
    assert SECRET_CONTENT not in resp.text


def test_revoked_consent_is_forbidden(world, make_client):
    user = world.user("dev@x.dev", private_enabled=True)
    repo = world.repo(user, private=True)
    world.consent(user, repo, revoked=True)
    world.report(repo, EVIDENCE)
    client = make_client(user, StubSource(None))

    assert (
        score(client, role="backend_developer", repository_id=repo.id).status_code
        == 403
    )


def test_other_users_repository_is_not_found(world, make_client):
    owner = world.user("owner@x.dev")
    intruder = world.user("intruder@x.dev")
    repo = world.repo(owner)
    world.verification(owner, repo)
    world.report(repo, EVIDENCE)
    client = make_client(intruder, StubSource(None))

    resp = score(client, role="backend_developer", repository_id=repo.id)

    assert resp.status_code == 404
    assert SECRET_CONTENT not in resp.text


def test_fork_with_same_commit_adds_no_evidence(world, db, make_client):
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, EVIDENCE)
    client = make_client(user, StubSource(None))
    before = _body(client)

    fork = world.repo(user)
    fork.is_fork = True
    db.commit()
    world.verification(user, fork)
    world.report(fork, EVIDENCE, confidence=0.99)
    after = _body(client)

    def core(body):
        return (
            body["status"],
            body["role_score"],
            body["coverage"],
            body["confidence"],
            [(c["key"], c["score"], c["confidence"]) for c in body["criteria"]],
            body["evidence_refs"],
        )

    assert core(after) == core(before)
