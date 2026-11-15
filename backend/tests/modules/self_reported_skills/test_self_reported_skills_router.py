"""Tests for self-reported skills and evidence CRUD endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.modules.self_reported_skills.models  # noqa: F401
import app.modules.users.models  # noqa: F401
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_session
from app.modules.self_reported_skills.models import (
    SelfReportedSkill,
    SelfReportedSkillEvidence,
)
from app.modules.self_reported_skills.router import router
from app.modules.users.models import User


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_ita(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS ita")
        cursor.close()

    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            SelfReportedSkill.__table__,
            SelfReportedSkillEvidence.__table__,
        ],
    )

    with Session(engine) as session:
        yield session

    Base.metadata.drop_all(
        bind=engine,
        tables=[
            SelfReportedSkillEvidence.__table__,
            SelfReportedSkill.__table__,
            User.__table__,
        ],
    )
    engine.dispose()


@pytest.fixture
def users(db):
    owner = User(
        id=1,
        email="owner@example.com",
        full_name="Owner",
        hashed_password="hashed_pw_placeholder",
    )
    other = User(
        id=2,
        email="other@example.com",
        full_name="Other",
        hashed_password="hashed_pw_placeholder",
    )
    db.add_all([owner, other])
    db.commit()
    return owner, other


def make_client(db, user):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    app.dependency_overrides[get_current_user] = lambda: user

    def override_get_session():
        yield db

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


@pytest.fixture
def client(db, users):
    return make_client(db, users[0])


@pytest.fixture
def other_client(db, users):
    return make_client(db, users[1])


def create_skill(client, name="Python"):
    response = client.post(
        "/api/v1/self-reported-skills",
        json={
            "skill_name": name,
            "description": "Personal skill description",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_evidence(client, skill_id):
    response = client.post(
        f"/api/v1/self-reported-skills/{skill_id}/evidence",
        json={
            "title": "Python project",
            "description": "Personal project evidence",
            "url": "https://example.com/project",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_skill_crud(client):
    created = create_skill(client)

    assert created["skill_name"] == "Python"
    assert created["source"] == "self-reported"
    assert created["status"] == "self-reported"
    assert created["evidence"] == []

    skill_id = created["id"]

    response = client.get("/api/v1/self-reported-skills")
    assert response.status_code == 200
    assert any(item["id"] == skill_id for item in response.json())

    response = client.get(f"/api/v1/self-reported-skills/{skill_id}")
    assert response.status_code == 200
    assert response.json()["skill_name"] == "Python"

    response = client.patch(
        f"/api/v1/self-reported-skills/{skill_id}",
        json={
            "skill_name": "Advanced Python",
            "description": "Updated description",
        },
    )
    assert response.status_code == 200
    assert response.json()["skill_name"] == "Advanced Python"
    assert response.json()["source"] == "self-reported"
    assert response.json()["status"] == "self-reported"

    response = client.delete(f"/api/v1/self-reported-skills/{skill_id}")
    assert response.status_code == 204

    response = client.get(f"/api/v1/self-reported-skills/{skill_id}")
    assert response.status_code == 404


def test_evidence_crud(client):
    skill = create_skill(client)
    skill_id = skill["id"]

    evidence = create_evidence(client, skill_id)
    evidence_id = evidence["id"]

    assert evidence["skill_id"] == skill_id
    assert evidence["source"] == "self-reported"
    assert evidence["status"] == "self-reported"

    response = client.patch(
        f"/api/v1/self-reported-skills/{skill_id}/evidence/{evidence_id}",
        json={
            "title": "Updated project evidence",
            "description": "Updated description",
            "url": "https://example.com/updated",
        },
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated project evidence"
    assert response.json()["source"] == "self-reported"
    assert response.json()["status"] == "self-reported"

    response = client.delete(
        f"/api/v1/self-reported-skills/{skill_id}/evidence/{evidence_id}"
    )
    assert response.status_code == 204

    response = client.get(f"/api/v1/self-reported-skills/{skill_id}")
    assert response.status_code == 200
    assert response.json()["evidence"] == []


def test_skill_list_only_returns_current_owner_data(client, other_client):
    owner_skill = create_skill(client, "Python")
    other_skill = create_skill(other_client, "Java")

    owner_response = client.get("/api/v1/self-reported-skills")
    other_response = other_client.get("/api/v1/self-reported-skills")

    assert owner_response.status_code == 200
    assert [item["id"] for item in owner_response.json()] == [owner_skill["id"]]

    assert other_response.status_code == 200
    assert [item["id"] for item in other_response.json()] == [other_skill["id"]]


def test_other_user_cannot_access_or_modify_skill(client, other_client):
    skill = create_skill(client)
    skill_id = skill["id"]

    response = other_client.get(f"/api/v1/self-reported-skills/{skill_id}")
    assert response.status_code == 404

    response = other_client.patch(
        f"/api/v1/self-reported-skills/{skill_id}",
        json={"skill_name": "Unauthorized update"},
    )
    assert response.status_code == 404

    response = other_client.delete(f"/api/v1/self-reported-skills/{skill_id}")
    assert response.status_code == 404


def test_other_user_cannot_access_or_modify_evidence(client, other_client):
    skill = create_skill(client)
    evidence = create_evidence(client, skill["id"])

    skill_id = skill["id"]
    evidence_id = evidence["id"]

    response = other_client.patch(
        f"/api/v1/self-reported-skills/{skill_id}/evidence/{evidence_id}",
        json={"title": "Unauthorized update"},
    )
    assert response.status_code == 404

    response = other_client.delete(
        f"/api/v1/self-reported-skills/{skill_id}/evidence/{evidence_id}"
    )
    assert response.status_code == 404

    response = other_client.post(
        f"/api/v1/self-reported-skills/{skill_id}/evidence",
        json={"title": "Unauthorized evidence"},
    )
    assert response.status_code == 404


def test_client_cannot_set_verified_source_or_status(client):
    response = client.post(
        "/api/v1/self-reported-skills",
        json={
            "skill_name": "Python",
            "source": "verified",
            "status": "verified",
        },
    )
    assert response.status_code == 422

    skill = create_skill(client)

    response = client.post(
        f"/api/v1/self-reported-skills/{skill['id']}/evidence",
        json={
            "title": "Evidence",
            "source": "verified",
            "status": "verified",
        },
    )
    assert response.status_code == 422


def test_blank_skill_name_and_evidence_title_are_rejected(client):
    response = client.post(
        "/api/v1/self-reported-skills",
        json={"skill_name": "   "},
    )
    assert response.status_code == 422

    skill = create_skill(client)

    response = client.post(
        f"/api/v1/self-reported-skills/{skill['id']}/evidence",
        json={"title": "   "},
    )
    assert response.status_code == 422
