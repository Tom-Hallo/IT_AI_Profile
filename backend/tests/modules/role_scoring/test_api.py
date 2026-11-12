"""Test API Role Scoring (PBI-017): auth, consent, isolation, rò rỉ, trạng thái."""

from __future__ import annotations

import json

import pytest

from app.modules.role_scoring.skill_adapter import RawSkillSnapshot
from tests.modules.role_scoring.conftest import (
    SECRET_CONTENT,
    SECRET_RATIONALE,
    StubSource,
)

BASE = "/api/v1/role-scoring"
SKILL_SECRET = "SKILL_REF_RATIONALE_SECRET"

FE_SEPARATION = (
    "frontend_backend_separation",
    "frontend/package.json",
    "manifest",
)
API = ("api_service", "backend/app/api/router.py", "source_code")
LAYERED = ("layered_architecture", "backend/app/services/s.py", "directory_structure")


def frontend_snapshot(user_id: int, repo_id: int) -> RawSkillSnapshot:
    def item(key, score):
        return {
            "skill_key": key,
            "score": score,
            "confidence": 80,
            "rationale": SKILL_SECRET,
            "evidence_refs": [
                {
                    "evidence_id": f"sk-{key}",
                    "repository_id": repo_id,
                    "file_path": f"src/{key}.ts",
                    "rationale": SKILL_SECRET,
                }
            ],
        }

    return RawSkillSnapshot(
        user_id,
        {
            "snapshot_ref": "snap-fe",
            "repository_ids": [str(repo_id)],
            "items": [item("typescript", 90), item("react", 80), item("vite", 60)],
        },
    )


def score(client, role="frontend_developer", **params):
    return client.get(f"{BASE}/roles/{role}/score", params=params)


# ------------------------------------------------------------------ happy path


def test_frontend_role_end_to_end_breakdown(world, db, make_client):
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [FE_SEPARATION])
    client = make_client(user, StubSource(frontend_snapshot(user.id, repo.id)))

    resp = score(client, repository_id=repo.id)

    assert resp.status_code == 200, resp.text
    assert resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert body["status"] == "SCORED"
    assert body["role_score"] is not None and 0 <= body["role_score"] <= 100
    assert body["calibration_status"] == "proposed_unvalidated"
    keys = {c["key"]: c for c in body["criteria"]}
    assert keys["frontend_language"]["type"] == "SKILL"
    assert keys["frontend_language"]["skill_key_used"] == "typescript"
    assert keys["frontend_backend_separation"]["type"] == "ARCHITECTURE"
    assert keys["frontend_backend_separation"]["status"] == "SCORED"
    assert keys["frontend_language"]["description"]
    assert body["inputs"]["skill_snapshot"]["snapshot_ref"] == "snap-fe"
    assert body["inputs"]["architecture"]["repositories"][0]["contribution_verified"]
    assert body["inputs"]["architecture"]["report_ref"].startswith("analysis_report:")
    arch_ref = keys["frontend_backend_separation"]["evidence_refs"][0]
    assert arch_ref["file_path"] == "frontend/package.json"
    assert arch_ref["commit_sha"] == "a" * 40
    assert arch_ref["verified"] is True


def test_no_private_content_or_rationale_in_response(world, db, make_client):
    user = world.user("dev@x.dev", private_enabled=True)
    repo = world.repo(user, private=True)
    world.consent(user, repo)
    world.verification(user, repo)
    world.report(repo, [FE_SEPARATION])
    client = make_client(user, StubSource(frontend_snapshot(user.id, repo.id)))

    resp = score(client, repository_id=repo.id)

    assert resp.status_code == 200
    raw = resp.text
    for secret in (SECRET_CONTENT, SECRET_RATIONALE, SKILL_SECRET):
        assert secret not in raw
    assert "matched_content" not in raw and "line_number" not in raw
    assert "rationale" not in json.dumps(
        [r for c in resp.json()["criteria"] for r in c["evidence_refs"]]
    )


def test_roles_endpoint_lists_extensible_rubrics(world, db, make_client):
    user = world.user("dev@x.dev")
    client = make_client(user)

    resp = client.get(f"{BASE}/roles")

    assert resp.status_code == 200
    roles = {r["role_key"]: r for r in resp.json()["roles"]}
    assert {"backend_developer", "frontend_developer"} <= set(roles)
    weights = sum(c["weight"] for c in roles["backend_developer"]["criteria"])
    assert weights == pytest.approx(1.0)
    assert roles["backend_developer"]["calibration_status"] == "proposed_unvalidated"


# ------------------------------------------------------------ missing data paths


def test_pbi016_not_wired_returns_unknown_skills_not_fake_scores(
    world, db, make_client
):
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [FE_SEPARATION])
    app_client = make_client(user)  # StubSource(None) = chưa có snapshot

    body = score(app_client, repository_id=repo.id).json()

    assert body["status"] in {"INSUFFICIENT", "UNKNOWN"}
    assert body["role_score"] is None
    skill = [c for c in body["criteria"] if c["type"] == "SKILL"]
    assert skill and all(c["score"] is None and c["status"] == "UNKNOWN" for c in skill)
    assert body["inputs"]["skill_snapshot"]["status"] == "MISSING"


def test_no_analysis_and_no_snapshot_is_unknown_not_zero(world, db, make_client):
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    client = make_client(user)

    body = score(client, role="backend_developer", repository_id=repo.id).json()

    assert body["status"] == "UNKNOWN"
    assert body["role_score"] is None
    assert body["coverage"] == 0
    assert body["inputs"]["architecture"]["status"] == "NOT_ANALYZED"


def test_directory_names_do_not_become_architecture_quality(world, db, make_client):
    """Rubric backend yêu cầu layered_structure; analyzer chỉ suy ra nó từ tên thư mục
    → bị loại, kết quả phải INSUFFICIENT chứ không được 'điểm kiến trúc'."""
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [API, LAYERED])
    client = make_client(user)

    body = score(client, role="backend_developer", repository_id=repo.id).json()

    layered = next(c for c in body["criteria"] if c["key"] == "layered_structure")
    assert layered["status"] == "UNKNOWN" and layered["score"] is None
    assert "layered_structure" in body["required_unmet"]
    assert body["role_score"] is None
    codes = {x["code"] for x in body["limitations"]}
    assert "EVIDENCE_SOURCE_EXCLUDED" in codes


def test_unverified_contribution_evidence_is_excluded_by_engine(world, db, make_client):
    user = world.user("dev@x.dev")
    repo = world.repo(user)  # chưa xác minh đóng góp
    world.report(repo, [FE_SEPARATION])
    client = make_client(user, StubSource(frontend_snapshot(user.id, repo.id)))

    body = score(client, repository_id=repo.id).json()

    crit = next(
        c for c in body["criteria"] if c["key"] == "frontend_backend_separation"
    )
    assert crit["status"] != "SCORED"
    assert any(e["reason"] == "UNVERIFIED" for e in crit["excluded_evidence"])
    assert "CONTRIBUTION_NOT_VERIFIED" in {x["code"] for x in body["limitations"]}


# ------------------------------------------------------- authentication & authz


def test_unauthenticated_request_is_rejected(db, make_client):
    client = make_client(user=None)
    assert client.get(f"{BASE}/roles").status_code == 401
    assert score(client).status_code == 401


def test_other_users_repository_returns_404(world, db, make_client):
    owner = world.user("owner@x.dev")
    attacker = world.user("attacker@x.dev")
    repo = world.repo(owner)
    world.report(repo, [FE_SEPARATION])
    source = StubSource(frontend_snapshot(attacker.id, repo.id))
    client = make_client(attacker, source)

    resp = score(client, repository_id=repo.id)

    assert resp.status_code == 404
    assert source.calls == 0  # dừng trước khi chạm PBI-016
    assert "frontend/package.json" not in resp.text


def test_private_repo_without_consent_returns_403(world, db, make_client):
    user = world.user("dev@x.dev", private_enabled=True)
    repo = world.repo(user, private=True)
    world.report(repo, [FE_SEPARATION])
    client = make_client(user)

    resp = score(client, repository_id=repo.id)

    assert resp.status_code == 403
    assert "frontend/package.json" not in resp.text


def test_revoked_consent_returns_403(world, db, make_client):
    user = world.user("dev@x.dev", private_enabled=True)
    repo = world.repo(user, private=True)
    world.consent(user, repo, revoked=True)
    world.report(repo, [FE_SEPARATION])
    client = make_client(user)

    assert score(client, repository_id=repo.id).status_code == 403


def test_snapshot_referencing_revoked_private_repo_is_dropped(world, db, make_client):
    user = world.user("dev@x.dev", private_enabled=True)
    public = world.repo(user)
    private = world.repo(user, private=True)
    world.consent(user, private, revoked=True)
    world.verification(user, public)
    world.report(public, [FE_SEPARATION])
    client = make_client(user, StubSource(frontend_snapshot(user.id, private.id)))

    body = score(client, repository_id=public.id).json()

    assert body["inputs"]["skill_snapshot"]["status"] == "FORBIDDEN"
    assert body["role_score"] is None
    assert "sk-typescript" not in json.dumps(body)


def test_snapshot_of_another_user_is_not_used(world, db, make_client):
    user = world.user("dev@x.dev")
    other = world.user("other@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [FE_SEPARATION])
    client = make_client(user, StubSource(frontend_snapshot(other.id, repo.id)))

    body = score(client, repository_id=repo.id).json()

    assert body["inputs"]["skill_snapshot"]["status"] == "FORBIDDEN"
    assert body["role_score"] is None


def test_implicit_scope_skips_private_without_consent(world, db, make_client):
    user = world.user("dev@x.dev", private_enabled=True)
    public = world.repo(user)
    private = world.repo(user, private=True)
    world.verification(user, public)
    world.report(public, [FE_SEPARATION])
    world.report(private, [API])
    client = make_client(user)

    resp = score(client)

    assert resp.status_code == 200
    repos = {
        r["repository_id"]: r["status"]
        for r in resp.json()["inputs"]["architecture"]["repositories"]
    }
    assert repos[private.id] == "SKIPPED_PRIVATE_CONSENT_REQUIRED"
    assert repos[public.id] == "USED"
    assert "api/router.py" not in resp.text


# ------------------------------------------------------------------ validation


def test_unknown_role_returns_404(world, db, make_client):
    user = world.user("dev@x.dev")
    assert score(make_client(user), role="astronaut").status_code == 404


def test_unknown_rubric_version_returns_404(world, db, make_client):
    user = world.user("dev@x.dev")
    resp = score(make_client(user), rubric_version="9.9.9")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"repository_id": 0},
        {"repository_id": -4},
        {"repository_id": "abc"},
        {"rubric_version": "latest"},
        {"snapshot_ref": ""},
    ],
)
def test_invalid_query_params_return_422(world, db, make_client, params):
    user = world.user("dev@x.dev")
    assert score(make_client(user), **params).status_code == 422


def test_pbi016_infrastructure_failure_returns_503_without_detail(
    world, db, make_client
):
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    client = make_client(user, StubSource(error=RuntimeError("password=hunter2")))

    resp = score(client, repository_id=repo.id)

    assert resp.status_code == 503
    assert "hunter2" not in resp.text
