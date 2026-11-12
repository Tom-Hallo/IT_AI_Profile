"""Exercise the PBI-019 reads with migrated PostgreSQL and real access guards."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.security import encrypt_token
from app.modules.analysis.models import (
    CollaborationAnalysis,
    CollaborationEvidence,
    RepositoryVerification,
)
from app.modules.auth.models import OAuthAccount
from tests.modules.role_scoring.test_scoped_postgres import (
    API_PATH,
    ENDPOINT,
    add_skill,
)

PREFIX = "/api/v1/repositories"


@pytest.fixture
def db(temp_database_url, alembic_cli):
    result = alembic_cli("upgrade", "head", database_url=temp_database_url)
    assert result.returncode == 0, result.stderr
    engine = create_engine(temp_database_url)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_dashboard_reports_and_role_scores_use_the_same_date_window(
    db, world, make_client
):
    owner = world.user("dashboard-owner@example.test")
    repo = world.repo(owner)
    world.verification(owner, repo)
    verification = db.scalar(select(RepositoryVerification))
    reports = []
    for day, score in ((5, 62), (10, 84)):
        report = world.report(
            repo, [("api_service", API_PATH, "source_code")], commit=str(day) * 20
        )
        report.analyzed_at = datetime(2026, 10, day, 23, 59, tzinfo=UTC)
        add_skill(db, owner, repo, report, verification, score=score)
        reports.append(report)

    client = make_client(owner)
    dashboard = f"{PREFIX}/{repo.id}/analysis/dashboard-report"
    window = {"date_from": "2026-10-05", "date_to": "2026-10-05"}
    response = client.get(dashboard, params=window)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["id"] == reports[0].id
    assert client.get(dashboard).json()["id"] == reports[1].id
    assert client.get(dashboard, params={"date_to": "2026-10-04"}).json() is None
    invalid = {"date_from": "2026-10-06", "date_to": "2026-10-05"}
    assert client.get(dashboard, params=invalid).status_code == 422
    assert client.get(ENDPOINT, params=invalid).status_code == 422

    scores = client.get(
        f"/api/v1/scoring/repositories/{repo.id}/skills",
        params={"report_id": reports[0].id},
    )
    assert scores.status_code == 200, scores.text
    assert scores.json()[0]["score"] == 62
    # The report pointer on verification rows must match the scored snapshot.
    verification.report_id = reports[0].id
    db.commit()
    scoped = client.get(ENDPOINT, params=window)
    assert scoped.status_code == 200, scoped.text
    public = scoped.json()["public"]["score"]
    assert public["inputs"]["architecture"]["report_ref"] == (
        f"analysis_report:{reports[0].id}"
    )
    skill = next(
        item for item in public["criteria"] if item["skill_key_used"] == "python"
    )
    assert skill["score"] == 62


def test_dashboard_denies_cross_user_and_private_without_consent(
    db, world, make_client
):
    owner = world.user("dashboard-private@example.test", private_enabled=True)
    outsider = world.user("dashboard-outsider@example.test")
    account = db.scalar(select(OAuthAccount).where(OAuthAccount.user_id == owner.id))
    account.encrypted_access_token = encrypt_token("fixture-private-access")
    db.commit()
    repo = world.repo(owner, private=True)
    world.report(repo, [])
    analysis = CollaborationAnalysis(repository_id=repo.id, user_id=owner.id)
    db.add(analysis)
    db.flush()
    db.add_all(
        [
            CollaborationEvidence(
                analysis_id=analysis.id,
                repository_id=repo.id,
                user_id=owner.id,
                evidence_type="pull_request",
                target_identifier=str(number),
                pr_number=number,
                recorded_at=datetime(2026, 10, number, tzinfo=UTC),
                rationale="Verified PR",
            )
            for number in (5, 10)
        ]
    )
    db.commit()
    later = CollaborationAnalysis(
        repository_id=repo.id,
        user_id=owner.id,
        analyzed_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    analysis.analyzed_at = datetime(2026, 10, 11, tzinfo=UTC)
    db.add(later)
    db.flush()
    db.add(
        CollaborationEvidence(
            analysis_id=later.id,
            repository_id=repo.id,
            user_id=owner.id,
            evidence_type="pull_request",
            target_identifier="20",
            pr_number=20,
            recorded_at=datetime(2026, 11, 1, tzinfo=UTC),
            rationale="Newer report",
        )
    )
    db.commit()
    dashboard = f"{PREFIX}/{repo.id}/analysis/dashboard-report"
    evidence = f"{PREFIX}/{repo.id}/collaboration/evidence"
    client = make_client(owner)
    for path in (dashboard, evidence):
        assert make_client().get(path).status_code == 401
        assert make_client(outsider).get(path).status_code == 404
        assert client.get(path).status_code == 403

    world.consent(owner, repo)
    assert client.get(dashboard).status_code == 200
    response = client.get(
        evidence,
        params={
            "evidence_type": "pull_request",
            "pr_number": 5,
            "date_to": "2026-10-05",
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert [item["pr_number"] for item in response.json()["items"]] == [5]
    assert (
        client.get(
            evidence, params={"date_from": "2026-10-06", "date_to": "2026-10-31"}
        ).json()["total"]
        == 1
    )
