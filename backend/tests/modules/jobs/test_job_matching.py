"""PBI-027 matching through actual scored reports and repository guards."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.modules.analysis.models import RepositoryVerification
from app.modules.consent.models import PrivateConsent
from app.modules.jobs.matching import JobMatchRequest
from app.modules.scoring.models import SkillScore
from tests.modules.role_scoring import conftest as fixtures
from tests.modules.role_scoring import test_scoped_postgres as pg_fixtures
from tests.modules.role_scoring.conftest import SECRET_CONTENT, SECRET_RATIONALE
from tests.modules.role_scoring.test_scoped_postgres import add_skill

db = pg_fixtures.db
world = fixtures.world
make_client = fixtures.make_client

ENDPOINT = "/api/v1/jobs/match"
HEADERS = {"Origin": settings.frontend_url}
SKILLS = [
    {"skill_key": " PYTHON ", "level": "preferred"},
    {"skill_key": "python", "level": "required"},
    {"skill_key": "Docker", "level": "required"},
]


def test_match_request_normalizes_and_rejects_assessment_injection():
    assert JobMatchRequest(skills=SKILLS).skills[0].skill_key == "python"
    aliases = [
        {"skill_key": key, "level": "required"} for key in ("C++", "Go", "Node.js")
    ]
    assert [item.skill_key for item in JobMatchRequest(skills=aliases).skills] == [
        "cpp",
        "golang",
        "nodejs",
    ]
    with pytest.raises(ValueError):
        JobMatchRequest.model_validate({"skills": SKILLS, "user_id": 22})
    with pytest.raises(ValueError):
        JobMatchRequest.model_validate({"skills": SKILLS, "scope": "all"})
    with pytest.raises(ValueError):
        JobMatchRequest.model_validate(
            {"skills": [{"skill_key": "   ", "level": "required"}]}
        )


def seed(db, world, owner, repo, *, scope, score, verifiable=True, suffix="a"):
    report = world.report(repo, [], commit=suffix * 40)
    report.scope = scope
    db.commit()
    world.verification(owner, repo)
    verification = db.scalar(
        select(RepositoryVerification)
        .where(RepositoryVerification.repository_id == repo.id)
        .order_by(RepositoryVerification.id.desc())
    )
    add_skill(db, owner, repo, report, verification, score=score)
    if not verifiable:
        skill = db.scalar(select(SkillScore).where(SkillScore.report_id == report.id))
        skill.breakdown = []
        db.commit()
    return report


def test_matching_is_deterministic_scope_safe_and_rechecks_consent(
    db, world, make_client
):
    owner = world.user("match-owner@example.test", private_enabled=True)
    other = world.user("match-other@example.test")
    public = world.repo(owner)
    private = world.repo(owner, private=True)
    outsider = world.repo(other)
    legacy = world.repo(owner)
    unsupported = world.repo(owner)
    world.consent(owner, private)
    report = seed(db, world, owner, public, scope="public", score=55)
    report.analyzed_at = datetime.now(UTC) - timedelta(days=100)
    db.commit()
    seed(db, world, owner, private, scope="private", score=90, suffix="b")
    seed(db, world, other, outsider, scope="public", score=100, suffix="c")
    seed(db, world, owner, legacy, scope="all", score=100, suffix="d")
    seed(db, world, owner, unsupported, scope="public", score=100, verifiable=False)

    assert (
        make_client()
        .post(ENDPOINT, json={"skills": SKILLS}, headers=HEADERS)
        .status_code
        == 401
    )
    client = make_client(owner)
    assert client.post(ENDPOINT, json={"skills": SKILLS}).status_code == 403

    def match(scope):
        response = client.post(
            ENDPOINT, json={"skills": SKILLS, "scope": scope}, headers=HEADERS
        )
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert SECRET_CONTENT not in response.text
        assert SECRET_RATIONALE not in response.text
        return response.json()

    extracted = client.post(
        "/api/v1/jobs/analyze",
        json={"text": "Backend Developer\nRequirements:\nPython and Docker"},
        headers=HEADERS,
    )
    assert extracted.status_code == 200, extracted.text
    assert {row["skill_key"] for row in extracted.json()["required_skills"]} == {
        "python",
        "docker",
    }

    result = match("public")
    assert result == match("public")
    assert result["stale_snapshot"] is True
    python, unknown = result["skills"]
    assert python["level"] == "required"
    assert (python["status"], python["score"]) == ("partial", 55)
    assert {ref["repository_id"] for ref in python["evidence"]} == {public.id}
    assert unknown["status"] == "unknown"
    assert unknown["score"] is None
    assert unknown["evidence"] == []
    assert result["required_matched_percent"] == 0

    assert match("private")["skills"][0]["status"] == "matched"
    combined = match("combined")
    assert combined["required_matched_percent"] == 50
    assert combined["skills"][0]["evidence"][0]["repository_id"] == private.id

    consent = db.scalar(select(PrivateConsent))
    consent.revoked_at = datetime.now(UTC)
    db.commit()
    denied = match("private")
    assert denied["skills"][0]["status"] == "unknown"
    assert denied["required_matched_percent"] is None
    assert denied["snapshot_refs"] == []
