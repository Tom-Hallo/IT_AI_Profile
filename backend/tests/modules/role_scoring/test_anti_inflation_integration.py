"""Chống tăng điểm giả qua dữ liệu còn lại
(guard, consent, verification, report/evidence) chạy bằng code và bảng thật.
"""

from __future__ import annotations

import pytest

from app.modules.self_reported_skills.models import (
    SelfReportedSkill,
    SelfReportedSkillEvidence,
)
from tests.modules.role_scoring.conftest import StubSource
from tests.modules.role_scoring.test_api import (
    API,
    FE_SEPARATION,
    LAYERED,
    frontend_snapshot,
    score,
)

DB_INTEGRATION = (
    "database_integration",
    "backend/alembic.ini",
    "manifest",
)
WORKERS = ("background_workers", "backend/app/workers/worker.py", "source_code")
EVIDENCE = [API, ("layered_architecture", "backend/app/services/s.py", "source_code")]


def _core(body: dict) -> tuple:
    return (
        body["status"],
        body["role_score"],
        body["coverage"],
        body["confidence"],
        [
            (c["key"], c["status"], c["score"], c["confidence"])
            for c in body["criteria"]
        ],
    )


def _scored(body: dict) -> list:
    return [
        (c["key"], c["score"], c["confidence"])
        for c in body["criteria"]
        if c["status"] == "SCORED"
    ]


def _baseline(world, make_client):
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, EVIDENCE)
    client = make_client(user, StubSource(None))
    resp = score(client, role="backend_developer")
    assert resp.status_code == 200, resp.text
    return user, repo, client, resp.json()


def test_baseline_scores_architecture_only_without_total(world, make_client):
    _, _, _, body = _baseline(world, make_client)
    # Thiếu skill snapshot (PBI-016) → không đủ coverage/required → không có tổng điểm.
    assert body["role_score"] is None
    assert body["status"] in {"INSUFFICIENT", "UNKNOWN"}


def test_adding_repositories_without_evidence_does_not_change_result(
    world, make_client
):
    user, _, client, before = _baseline(world, make_client)
    for _ in range(12):
        world.repo(user)  # công khai, đã link, CHƯA phân tích
    after = score(client, role="backend_developer").json()
    assert _core(after) == _core(before)
    assert after["evidence_refs"] == before["evidence_refs"]


def test_adding_unverified_repository_with_evidence_does_not_change_result(
    world, make_client
):
    user, _, client, before = _baseline(world, make_client)
    extra = world.repo(user)
    world.report(extra, [API, LAYERED, DB_INTEGRATION, WORKERS], commit="b" * 40)
    after = score(client, role="backend_developer").json()
    # Evidence chưa xác nhận có thể đổi UNKNOWN → INSUFFICIENT (có dữ liệu nhưng không
    # được tính), nhưng tuyệt đối không tạo điểm/coverage/confidence mới.
    assert _scored(after) == _scored(before)
    assert (after["role_score"], after["coverage"], after["confidence"]) == (
        before["role_score"],
        before["coverage"],
        before["confidence"],
    )
    assert any(
        lim["code"] == "CONTRIBUTION_NOT_VERIFIED" for lim in after["limitations"]
    )


def test_star_fork_and_size_counters_do_not_change_result(world, db, make_client):
    _, repo, client, before = _baseline(world, make_client)
    repo.stars_count, repo.forks_count, repo.size_kb = 50_000, 9_000, 10_000_000
    repo.open_issues_count = 4_000
    db.commit()
    after = score(client, role="backend_developer").json()
    assert _core(after) == _core(before)


def test_fork_with_same_commit_and_files_adds_no_score_or_evidence(
    world, db, make_client
):
    user, _, client, before = _baseline(world, make_client)
    fork = world.repo(user)
    fork.is_fork = True
    fork.fork_source = "upstream/project"
    db.commit()
    world.verification(user, fork)  # đóng góp đã xác nhận: vẫn không được tính thêm
    world.report(fork, EVIDENCE, confidence=0.99)  # cùng SHA mặc định + cùng file

    after = score(client, role="backend_developer").json()

    assert _core(after) == _core(before)
    assert after["evidence_refs"] == before["evidence_refs"]
    for crit in after["criteria"]:
        assert len(crit["evidence_refs"]) <= 1
    dup = [
        e
        for c in after["criteria"]
        for e in c["excluded_evidence"]
        if e["reason"] == "DUPLICATE"
    ]
    assert dup, "evidence của fork phải được ghi nhận là trùng"


def test_fork_with_new_commit_and_new_pattern_is_the_only_way_to_add_evidence(
    world, db, make_client
):
    """Đối chứng: chỉ evidence MỚI và đã xác nhận mới làm đổi kết quả."""
    user, _, client, before = _baseline(world, make_client)
    other = world.repo(user)
    world.verification(user, other)
    world.report(other, [DB_INTEGRATION, WORKERS], commit="c" * 40)
    after = score(client, role="backend_developer").json()

    status = {c["key"]: c["status"] for c in after["criteria"]}
    assert status["database_migration"] == "SCORED"
    assert status["background_processing"] == "SCORED"
    assert after["coverage"] > before["coverage"]


def test_activity_metric_in_snapshot_payload_is_rejected_not_scored(world, make_client):
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, EVIDENCE)
    raw = frontend_snapshot(user.id, repo.id)
    payload = dict(raw.payload)
    payload["commit_count"] = 100_000
    payload["lines_of_code"] = 10_000_000
    raw = type(raw)(user.id, payload)
    client = make_client(user, StubSource(raw))

    body = score(client, role="frontend_developer").json()

    assert body["inputs"]["skill_snapshot"]["status"] == "INVALID"
    assert body["role_score"] is None
    assert all(
        c["status"] == "UNKNOWN" for c in body["criteria"] if c["type"] == "SKILL"
    )


@pytest.mark.parametrize("repeat", [1, 25])
def test_repeating_identical_snapshot_evidence_does_not_inflate(
    world, make_client, repeat
):
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(
        repo, [("frontend_backend_separation", "frontend/package.json", "manifest")]
    )
    raw = frontend_snapshot(user.id, repo.id)
    payload = dict(raw.payload)
    for item in payload["items"]:
        item["evidence_refs"] = item["evidence_refs"] * repeat
    client = make_client(user, StubSource(type(raw)(user.id, payload)))

    body = score(client, role="frontend_developer", repository_id=repo.id).json()

    for crit in body["criteria"]:
        assert len(crit["evidence_refs"]) <= 1
    if repeat == 25:
        ref = score(
            make_client(user, StubSource(frontend_snapshot(user.id, repo.id))),
            role="frontend_developer",
            repository_id=repo.id,
        ).json()
        assert _core(body) == _core(ref)


def test_self_reported_skills_and_evidence_do_not_inflate_verified_score(
    world, db, make_client
):
    # Arrange: tạo baseline có Verified Score thực tế.
    user = world.user("dev@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [FE_SEPARATION])

    client = make_client(
        user,
        StubSource(frontend_snapshot(user.id, repo.id)),
    )

    before_response = score(
        client,
        role="frontend_developer",
        repository_id=repo.id,
    )

    assert before_response.status_code == 200, before_response.text
    before = before_response.json()

    assert before["status"] == "SCORED"
    assert before["role_score"] is not None

    # Act: thêm kỹ năng và minh chứng do người dùng tự khai báo.
    skill = SelfReportedSkill(
        user_id=user.id,
        skill_name="Python",
        description="User claims experience with Python",
    )
    db.add(skill)
    db.flush()

    evidence = SelfReportedSkillEvidence(
        skill_id=skill.id,
        user_id=user.id,
        title="Personal Python project",
        description="A self-reported project",
        url="https://example.test/python-project",
    )
    db.add(evidence)
    db.commit()

    # Chạy scoring lại với cùng verified snapshot.
    after_response = score(
        client,
        role="frontend_developer",
        repository_id=repo.id,
    )

    assert after_response.status_code == 200, after_response.text
    after = after_response.json()

    # Assert: dữ liệu tự khai báo không làm tăng Verified Score.
    assert after["status"] == before["status"]
    assert _core(after) == _core(before)
    assert after["evidence_refs"] == before["evidence_refs"]
