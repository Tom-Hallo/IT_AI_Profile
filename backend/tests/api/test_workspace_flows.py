"""Exercise workspace routes against genuine database state."""

from sqlalchemy import select

from app.core.config import settings
from app.modules.analysis.models import RepositoryVerification
from app.modules.cvs.models import CV
from app.modules.jobs.schemas import JobSearchResponse
from app.modules.jobs.search_service import JobSearchService
from app.modules.scoring.models import RubricVersion, SkillScore
from app.modules.scoring.snapshots import VERSION
from tests.modules.role_scoring import conftest as fixtures
from tests.modules.role_scoring import test_scoped_postgres as pg_fixtures

db = pg_fixtures.db
world = fixtures.world
make_client = fixtures.make_client

ORIGIN = {"Origin": settings.frontend_url}
API = "/api/v1"


def test_roadmap_creation_tracking_and_reevaluation(db, world, make_client):
    user = world.user("roadmap@example.test")
    repo = world.repo(user)
    report = world.report(repo, [])
    report.scope = "public"
    world.verification(user, repo)
    verification = db.scalar(
        select(RepositoryVerification).where(RepositoryVerification.user_id == user.id)
    )
    pg_fixtures.add_skill(db, user, repo, report, verification, score=70)
    skill = db.scalar(select(SkillScore).where(SkillScore.report_id == report.id))
    skill.rubric_id = db.scalar(
        select(RubricVersion.id).where(
            RubricVersion.kind == "language", RubricVersion.version == VERSION
        )
    )
    db.commit()

    client = make_client(user)
    response = client.post(
        f"{API}/career-roadmaps", json={"goal": "backend"}, headers=ORIGIN
    )
    assert response.status_code == 201, response.text
    generated = response.json()
    python = next(m for m in generated["milestones"] if m["skill"] == "python")
    assert python["current_score"] == 70
    assert python["evidence"][0]["repository_id"] == repo.id
    base = f"{API}/roadmap-tracking/{generated['id']}"
    result = client.get(base).json()
    assert len(result["milestones"]) == len(generated["milestones"])
    progress = next(m for m in result["milestones"] if m["external_key"] == "python")
    update = client.patch(
        f"{base}/milestones/{progress['id']}",
        json={"status": "in_progress", "expected_version": progress["version"]},
        headers=ORIGIN,
    )
    assert update.status_code == 200, update.text
    assert (
        client.post(f"{base}/re-evaluate", headers=ORIGIN).json()["suggestions"] == []
    )
    skill.score = 88
    db.commit()
    newer = client.post(f"{base}/re-evaluate", headers=ORIGIN)
    assert newer.status_code == 200, newer.text
    suggestion = newer.json()["suggestions"][0]
    repeat = client.post(f"{base}/re-evaluate", headers=ORIGIN)
    assert repeat.json() == newer.json()
    apply = client.post(f"{base}/suggestions/{suggestion['id']}/apply", headers=ORIGIN)
    assert apply.json()["state"] == "applied"
    history = client.get(f"{base}/milestones/{progress['id']}/history").json()
    assert [item["new_status"] for item in history] == ["in_progress", "completed"]


def test_ats_uses_current_owner_cv_and_returns_evidence(db, world, make_client):
    owner = world.user("ats@example.test")
    outsider = world.user("ats-outsider@example.test")
    cv = CV(
        user_id=owner.id,
        content={"source": "user_upload", "version": 2, "text": "Skills\nPython"},
    )
    db.add(cv)
    db.commit()
    payload = {"cv_id": cv.id, "jd_text": "Python and Docker"}
    path = f"{API}/ats-reviews/preview"
    result = make_client(owner).post(path, json=payload, headers=ORIGIN)
    assert result.status_code == 200
    assert result.json()["cv_version"] == 2
    assert result.json()["keyword_coverage"] == 50
    assert result.json()["checks"]["file_layout"] == "not_checked"
    assert (
        make_client(outsider).post(path, json=payload, headers=ORIGIN).status_code
        == 404
    )


def test_profile_share_can_be_read_and_revoked_across_sessions(world, make_client):
    user = world.user("share@example.test")
    owner = make_client(user)
    visitor = make_client()
    shares = f"{API}/profile/shares"
    created = owner.post(shares, json={"allowed_fields": ["full_name"]}, headers=ORIGIN)
    assert created.status_code == 201, created.text
    share = created.json()
    assert owner.get(shares).json() == [
        {"id": share["id"], "allowed_fields": ["full_name"]}
    ]
    public = f"{API}/public/profiles/{share['token']}"
    result = visitor.get(public)
    assert result.json() == {"full_name": user.full_name}
    assert result.headers["cache-control"] == "no-store"
    assert owner.delete(f"{shares}/{share['id']}", headers=ORIGIN).status_code == 204
    assert visitor.get(public).status_code == 404


def test_explicit_job_search_reaches_provider(world, make_client, monkeypatch):
    user = world.user("search@example.test")
    requests = []

    def lookup(_self, request):
        requests.append(request.query)
        return JobSearchResponse(total=0, searched_at="2026-11-20T00:00:00Z")

    monkeypatch.setattr(JobSearchService, "search", lookup)
    path = f"{API}/jobs/search"
    assert (
        make_client().post(path, json={"query": "python"}, headers=ORIGIN).status_code
        == 401
    )
    assert requests == []
    response = make_client(user).post(path, json={"query": "python"}, headers=ORIGIN)
    assert response.status_code == 200
    assert requests == ["python"]


def test_roadmap_submission_relevance_dedup_and_revoked_visibility(
    db, world, make_client
):
    user = world.user("roadmap-evidence@example.test")
    repo = world.repo(user)
    repo.full_name = "example/roadmap"
    report = world.report(repo, [])
    report.scope = "public"
    world.verification(user, repo)
    verification = db.scalar(
        select(RepositoryVerification).where(RepositoryVerification.user_id == user.id)
    )
    pg_fixtures.add_skill(db, user, repo, report, verification, score=70)
    skill = db.scalar(select(SkillScore).where(SkillScore.report_id == report.id))
    skill.rubric_id = db.scalar(
        select(RubricVersion.id).where(
            RubricVersion.kind == "language", RubricVersion.version == VERSION
        )
    )
    db.commit()
    client = make_client(user)
    road = client.post(
        f"{API}/career-roadmaps", json={"goal": "backend"}, headers=ORIGIN
    ).json()
    base = f"{API}/roadmap-tracking/{road['id']}"
    tracked = client.get(base).json()["milestones"]
    python = next(m for m in tracked if m["external_key"] == "python")
    docker = next(m for m in tracked if m["external_key"] == "docker")
    url = f"https://github.com/example/roadmap/commit/{report.commit_sha}"
    python_path = f"{base}/milestones/{python['id']}"
    docker_path = f"{base}/milestones/{docker['id']}"

    low = client.post(
        f"{python_path}/evidence", json={"evidence_url": url}, headers=ORIGIN
    )
    assert low.status_code == 200, low.text
    assert low.json()["verification_status"] == "self_reported"
    assert low.json()["status"] == "in_progress"

    skill.score = 88
    db.commit()
    wrong = client.post(
        f"{docker_path}/evidence", json={"evidence_url": url}, headers=ORIGIN
    )
    assert wrong.json()["verification_status"] == "self_reported"
    assert wrong.json()["status"] == "in_progress"

    verified = client.post(
        f"{python_path}/evidence", json={"evidence_url": url}, headers=ORIGIN
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verification_status"] == "verified"
    assert verified.json()["status"] == "completed"
    assert verified.json()["duplicate"] is True
    duplicate = client.post(
        f"{python_path}/evidence",
        json={"evidence_url": url.replace("example", "Example") + "/"},
        headers=ORIGIN,
    )
    assert duplicate.json()["duplicate"] is True
    tracking = client.get(base).json()
    current = next(m for m in tracking["milestones"] if m["id"] == python["id"])
    assert len([e for e in current["evidence"] if e.get("url")]) == 1
    assert current["verification_status"] == "verified"
    history = client.get(f"{python_path}/history").json()
    assert len(history) == 2

    repo.private = True
    db.commit()
    tracking = client.get(base)
    assert tracking.status_code == 200, tracking.text
    assert url not in tracking.text
    current = next(
        m for m in tracking.json()["milestones"] if m["id"] == python["id"]
    )
    assert current["verification_status"] != "verified"
    career = client.get(f"{API}/career-roadmaps/{road['id']}")
    assert url not in career.text
    history = client.get(f"{python_path}/history")
    assert url not in history.text


def test_roadmap_stale_suggestion_rejected_after_snapshot_changes(
    db, world, make_client
):
    user = world.user("roadmap-stale@example.test")
    repo = world.repo(user)
    report = world.report(repo, [])
    report.scope = "public"
    world.verification(user, repo)
    verification = db.scalar(
        select(RepositoryVerification).where(RepositoryVerification.user_id == user.id)
    )
    pg_fixtures.add_skill(db, user, repo, report, verification, score=70)
    skill = db.scalar(select(SkillScore).where(SkillScore.report_id == report.id))
    skill.rubric_id = db.scalar(
        select(RubricVersion.id).where(
            RubricVersion.kind == "language", RubricVersion.version == VERSION
        )
    )
    db.commit()
    client = make_client(user)
    road = client.post(
        f"{API}/career-roadmaps", json={"goal": "backend"}, headers=ORIGIN
    ).json()
    base = f"{API}/roadmap-tracking/{road['id']}"
    skill.score = 88
    db.commit()
    result = client.post(f"{base}/re-evaluate", headers=ORIGIN)
    assert result.status_code == 200, result.text
    suggestion = result.json()["suggestions"][0]
    skill.score = 60
    db.commit()
    response = client.post(
        f"{base}/suggestions/{suggestion['id']}/apply", headers=ORIGIN
    )
    assert response.status_code == 409, response.text
    tracking = client.get(base).json()
    current = next(s for s in tracking["suggestions"] if s["id"] == suggestion["id"])
    assert current["state"] == "stale"
    assert current["evidence"] == []
    assert all(m["status"] != "completed" for m in tracking["milestones"])
