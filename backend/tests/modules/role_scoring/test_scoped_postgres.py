"""Exercise the scoped endpoint with real SQL and current repository consent."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.modules.analysis.models import RepositoryVerification, VerificationEvidence
from app.modules.consent.models import PrivateConsent
from app.modules.scoring.models import RubricVersion, SkillScore
from tests.modules.role_scoring.conftest import SECRET_CONTENT, SECRET_RATIONALE

ENDPOINT = "/api/v1/role-scoring/roles/backend_developer/score/scoped"
API_PATH = "backend/app/api/public.py"


@pytest.fixture
def db(temp_database_url, alembic_cli):
    result = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert result.returncode == 0, result.stderr
    engine = create_engine(temp_database_url)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_skill(db, user, repo, report, verification, *, score=82):
    verification.report_id = report.id
    contribution = VerificationEvidence(
        verification_id=verification.id,
        repository_id=repo.id,
        user_id=user.id,
        evidence_type="commit",
        target_identifier=report.commit_sha,
        verification_status="verified",
        rationale=SECRET_RATIONALE,
    )
    db.add(contribution)
    db.flush()
    rubric = db.scalar(select(RubricVersion).where(RubricVersion.kind == "language"))
    assert rubric is not None
    db.add(
        SkillScore(
            user_id=user.id,
            repository_id=repo.id,
            report_id=report.id,
            rubric_id=rubric.id,
            commit_sha=report.commit_sha,
            kind="language",
            technology="Python",
            status="Scored",
            score=score,
            breakdown=[
                {
                    "criterion": "confidence",
                    "normalized_value": 0.65,
                    "evidence_kind": "verification",
                    "evidence_ids": [contribution.id],
                }
            ],
            explanation=SECRET_RATIONALE,
        )
    )
    db.commit()


def test_scopes_use_real_scores_and_isolate_private_data(db, world, make_client):
    owner = world.user("pbi18-owner@example.test", private_enabled=True)
    other = world.user("pbi18-other@example.test")
    public = world.repo(owner)
    private = world.repo(owner, private=True)
    denied = world.repo(owner, private=True)
    outsider = world.repo(other)
    world.consent(owner, private)
    for repo, path in (
        (public, API_PATH),
        (private, "backend/app/services/private_only.py"),
        (denied, "backend/app/api/denied_secret.py"),
        (outsider, "backend/app/api/foreign_secret.py"),
    ):
        user = other if repo.id == outsider.id else owner
        world.verification(user, repo)
        report = world.report(
            repo,
            [
                ("api_service", API_PATH, "source_code"),
                ("layered_architecture", path, "source_code"),
            ],
        )
        verification = db.scalar(
            select(RepositoryVerification).where(
                RepositoryVerification.repository_id == repo.id
            )
        )
        add_skill(db, user, repo, report, verification)

    assert make_client().get(ENDPOINT).status_code == 401
    client = make_client(owner)
    response = client.get(ENDPOINT)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert all(body[scope]["available"] for scope in ("public", "private", "combined"))
    assert body["dedup_summary"]["duplicates_removed"] == 1
    assert body["public"]["score"]["inputs"]["skill_snapshot"]["snapshot_ref"]
    assert body["private"]["score"]["inputs"]["skill_snapshot"]["snapshot_ref"]
    assert (
        body["public"]["score"]["inputs"]["skill_snapshot"]["snapshot_ref"]
        != (body["private"]["score"]["inputs"]["skill_snapshot"]["snapshot_ref"])
    )
    skill = next(
        criterion
        for criterion in body["public"]["score"]["criteria"]
        if criterion["skill_key_used"] == "python"
    )
    assert skill["score"] == 82
    assert 0 < skill["confidence"] <= 65
    assert "private_only.py" not in str(body["public"])
    assert "private_only.py" in str(body["private"])
    assert "private_only.py" in str(body["combined"])
    for marker in (
        "denied_secret.py",
        "foreign_secret.py",
        SECRET_CONTENT,
        SECRET_RATIONALE,
    ):
        assert marker not in response.text

    outsider_body = make_client(other).get(ENDPOINT).json()
    assert outsider_body["private"]["available"] is False
    assert "private_only.py" not in str(outsider_body)

    consent = db.scalar(
        select(PrivateConsent).where(PrivateConsent.repository_id == private.id)
    )
    consent.revoked_at = datetime.now(UTC)
    db.commit()
    revoked = client.get(ENDPOINT)
    assert revoked.status_code == 200
    assert revoked.json()["private"]["available"] is False
    assert "private_only.py" not in revoked.text


def test_missing_evidence_returns_insufficient(world, make_client):
    user = world.user("empty-pbi18@example.test")
    world.repo(user)
    response = make_client(user).get(ENDPOINT)
    assert response.status_code == 200, response.text
    result = response.json()
    for scope in ("public", "combined"):
        assert result[scope]["score"]["status"] == "INSUFFICIENT"
        assert result[scope]["score"]["role_score"] is None
