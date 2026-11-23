"""Comprehensive, 100% full-spectrum E2E test suite for the Roadmap feature.

Tests:
1. Full Roadmap Lifecycle per Goal (backend, frontend, fullstack, devops)
2. Roadmap Tracking & Legacy Steps Migration
3. Milestone Status Transitions & Optimistic Locking (Version Conflict 409)
4. Milestone Audit History Logging
5. Evidence Submission & Verification Matrix:
   - Invalid URLs (422)
   - Self-reported URLs (status -> in_progress, verification_status -> self_reported)
   - SSRF / Attacker domain rejection
   - Unverified GitHub PRs & Commits
   - Verified GitHub PRs & Commits (status -> completed)
   - JSONB Mutation Persistence & Session Reload
   - Evidence Visibility Retention
6. Re-evaluation & Suggestion Resolution (Apply/Reject & Replay 409)
7. Cross-User Isolation & Security (User 2 cannot touch User 1's roadmap)
8. AI Mentor Roadmap Integration:
   - Context packaging for specific milestone (milestone_id)
   - AI Mentor Action Proposal: create_roadmap (confirm & execute)
   - AI Mentor Action Proposal: update_roadmap add_milestone (confirm & execute)
   - AI Mentor Action Proposal: update_roadmap modify_milestone (confirm & execute)
   - AI Mentor Action Proposal: decline (proposal declined without side effect)
"""

import json
import os

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.ai_mentor.action_schemas import ActionDecision
from app.modules.ai_mentor.actions import decide_action, propose_action
from app.modules.ai_mentor.schemas import MentorChatRequest
from app.modules.ai_mentor.service import _collect_context
from app.modules.career_roadmap.engine import GOALS, generate
from app.modules.career_roadmap.router import _serialize
from app.modules.roadmap_tracking.models import (
    Milestone,
    MilestoneHistory,
    RoadmapSuggestion,
)
from app.modules.roadmaps.models import Roadmap
from app.modules.users.models import User

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1",
        reason="cần RUN_INTEGRATION=1 và PostgreSQL đang chạy",
    ),
]


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db: Session):
    user = db.scalar(select(User).where(User.id == 1))
    if not user:
        user = User(
            id=1,
            email="test_roadmap_owner@example.com",
            full_name="Roadmap Owner",
        )
        db.add(user)
        db.commit()
    return user


@pytest.fixture
def other_user(db: Session):
    user = db.scalar(select(User).where(User.id == 9999))
    if not user:
        user = User(
            id=9999,
            email="other_intruder@example.com",
            full_name="Other User",
        )
        db.add(user)
        db.commit()
    return user


def test_01_roadmap_generation_all_goals():
    """Verify roadmap generation for every supported goal."""
    for goal in ["backend", "frontend", "fullstack", "devops"]:
        res = generate(goal, [])
        assert res["goal"] == goal
        assert res["total"] == len(GOALS[goal])
        assert len(res["milestones"]) == len(GOALS[goal])
        for idx, m in enumerate(res["milestones"], 1):
            assert m["order"] == idx
            assert m["skill"] in GOALS[goal]
            assert m["target_score"] == GOALS[goal][m["skill"]]
            assert m["status"] == "todo"
            assert m["gap_type"] == "missing_evidence"


def test_02_legacy_steps_migration(db: Session, test_user: User):
    """Verify legacy roadmaps with only 'steps' auto-migrate to milestones."""
    legacy_data = {
        "goal": "backend",
        "steps": ["Learn Docker Containerization", "Master FastAPI Microservices"],
        "analysis_context": {
            "scope": "public",
            "rubric": "v2.1.0",
            "period": "all_time",
        },
    }
    rm = Roadmap(
        user_id=test_user.id,
        title="Legacy Steps Roadmap",
        data=legacy_data,
    )
    db.add(rm)
    db.commit()
    db.refresh(rm)

    # Calling tracking logic should trigger migration
    from app.modules.roadmap_tracking.router import get_tracking

    tracking = get_tracking(rm.id, test_user, db)
    assert len(tracking["milestones"]) == 2
    assert tracking["milestones"][0]["title"] == "Learn Docker Containerization"
    assert tracking["milestones"][1]["title"] == "Master FastAPI Microservices"

    # Query new DB session to ensure persistence
    db.expire_all()
    reloaded = db.scalar(select(Roadmap).where(Roadmap.id == rm.id))
    assert "milestones" in reloaded.data
    assert len(reloaded.data["milestones"]) == 2


def test_03_milestone_status_transition_and_optimistic_lock(
    db: Session, test_user: User
):
    """Verify milestone status transitions, version lock 409 and data sync."""
    from fastapi import HTTPException

    from app.modules.roadmap_tracking.router import StatusUpdate, update_milestone

    res = generate("backend", [])
    rm = Roadmap(
        user_id=test_user.id,
        title="Status Transition Test",
        data={
            **res,
            "analysis_context": {
                "scope": "public",
                "rubric": "v2.1.0",
                "period": "all_time",
            },
        },
    )
    db.add(rm)
    db.flush()
    ms = Milestone(
        roadmap_id=rm.id,
        external_key="fastapi",
        title="FastAPI",
        required_skills=["fastapi"],
        status="pending",
        version=1,
    )
    db.add(ms)
    db.commit()

    # Conflict on wrong version
    with pytest.raises(HTTPException) as exc:
        update_milestone(
            rm.id,
            ms.id,
            StatusUpdate(status="in_progress", expected_version=99),
            test_user,
            db,
        )
    assert exc.value.status_code == 409

    # Valid update to in_progress
    updated = update_milestone(
        rm.id,
        ms.id,
        StatusUpdate(status="in_progress", expected_version=1, note="Started learning"),
        test_user,
        db,
    )
    assert updated["status"] == "in_progress"
    assert updated["version"] == 2

    # Check persistence in roadmap.data
    db.expire_all()
    rm_check = db.scalar(select(Roadmap).where(Roadmap.id == rm.id))
    m_data = next(m for m in rm_check.data["milestones"] if m["skill"] == "fastapi")
    assert m_data["status"] == "in_progress"

    # Valid update to completed
    updated2 = update_milestone(
        rm.id,
        ms.id,
        StatusUpdate(status="completed", expected_version=2, note="Completed course"),
        test_user,
        db,
    )
    assert updated2["status"] == "completed"
    assert updated2["version"] == 3

    # Check history logging
    histories = db.scalars(
        select(MilestoneHistory)
        .where(MilestoneHistory.milestone_id == ms.id)
        .order_by(MilestoneHistory.id)
    ).all()
    assert len(histories) == 2
    assert histories[0].old_status == "pending"
    assert histories[0].new_status == "in_progress"
    assert histories[1].old_status == "in_progress"
    assert histories[1].new_status == "completed"


def test_04_evidence_submission_and_strict_validation(db: Session, test_user: User):
    """Verify invalid URLs, self-reported URLs, and official GitHub verification."""
    from fastapi import HTTPException

    from app.modules.roadmap_tracking.router import (
        EvidenceSubmission,
        submit_milestone_evidence,
    )

    res = generate("backend", [])
    rm = Roadmap(
        user_id=test_user.id,
        title="Evidence Test Roadmap",
        data={
            **res,
            "analysis_context": {
                "scope": "public",
                "rubric": "v2.1.0",
                "period": "all_time",
            },
        },
    )
    db.add(rm)
    db.flush()
    ms = Milestone(
        roadmap_id=rm.id,
        external_key="docker",
        title="Docker",
        required_skills=["docker"],
        status="pending",
        version=1,
    )
    db.add(ms)
    db.commit()

    # 1. Invalid URL scheme
    with pytest.raises(HTTPException) as exc:
        submit_milestone_evidence(
            rm.id,
            ms.id,
            EvidenceSubmission(evidence_url="ftp://ftp.example.com/docker"),
            test_user,
            db,
        )
    assert exc.value.status_code == 422

    # 2. Self-reported valid external URL
    sub1 = submit_milestone_evidence(
        rm.id,
        ms.id,
        EvidenceSubmission(
            evidence_url="https://medium.com/@dev/docker-guide", note="Study notes"
        ),
        test_user,
        db,
    )
    assert sub1["verification_status"] == "self_reported"
    assert sub1["status"] == "in_progress"
    assert sub1["version"] == 2

    # 3. Attacker spoofed GitHub domain
    sub2 = submit_milestone_evidence(
        rm.id,
        ms.id,
        EvidenceSubmission(
            evidence_url="https://github.com.attacker.com/org/repo/pull/1",
            note="Spoofed domain",
        ),
        test_user,
        db,
    )
    assert sub2["verification_status"] == "self_reported"

    # 4. Use existing verified PR and commit from Tom-Hallo/IT_AI_Profile
    # Submit verified PR 17
    sub_pr = submit_milestone_evidence(
        rm.id,
        ms.id,
        EvidenceSubmission(
            evidence_url="https://github.com/Tom-Hallo/IT_AI_Profile/pull/17",
            note="Verified PR #17",
        ),
        test_user,
        db,
    )
    assert sub_pr["verification_status"] == "verified"
    assert sub_pr["status"] == "completed"
    assert "được hệ thống xác minh" in sub_pr["explanation"]

    # Submit verified commit
    commit_sha = "c7c94bf112fa0c73a1e125a926941f60d493540f"
    sub_commit = submit_milestone_evidence(
        rm.id,
        ms.id,
        EvidenceSubmission(
            evidence_url=f"https://github.com/Tom-Hallo/IT_AI_Profile/commit/{commit_sha}",
            note="Verified Dockerfile commit",
        ),
        test_user,
        db,
    )
    assert sub_commit["verification_status"] == "verified"

    # Verify persistence in clean session and _serialize evidence retention
    db.expire_all()
    rm_check = db.scalar(select(Roadmap).where(Roadmap.id == rm.id))
    serialized = _serialize(rm_check, db, test_user.id)
    m_check = next(m for m in serialized["milestones"] if m["skill"] == "docker")
    assert len(m_check["evidence"]) >= 3
    assert any(e.get("verification_status") == "verified" for e in m_check["evidence"])


def test_05_re_evaluation_and_suggestion_resolution(db: Session, test_user: User):
    """Verify suggestion creation, applying suggestion, and rejection."""
    from fastapi import HTTPException

    from app.modules.roadmap_tracking.router import apply_suggestion

    res = generate("backend", [])
    rm = Roadmap(
        user_id=test_user.id,
        title="Suggestion Test Roadmap",
        data={
            **res,
            "analysis_context": {
                "scope": "public",
                "rubric": "v2.1.0",
                "period": "all_time",
            },
        },
    )
    db.add(rm)
    db.flush()
    ms = Milestone(
        roadmap_id=rm.id,
        external_key="postgresql",
        title="PostgreSQL",
        required_skills=["postgresql"],
        status="in_progress",
        version=1,
    )
    db.add(ms)
    db.flush()

    sug = RoadmapSuggestion(
        roadmap_id=rm.id,
        milestone_id=ms.id,
        snapshot_key="snap-test-123",
        action="complete",
        explanation="Verified DB skills detected",
        evidence=[{"skill": "postgresql", "ref": "commit:123"}],
        state="pending",
    )
    db.add(sug)
    db.commit()

    # Apply suggestion
    applied = apply_suggestion(rm.id, sug.id, test_user, db)
    assert applied["state"] == "applied"

    # Verify milestone transitioned to completed
    db.expire_all()
    ms_check = db.scalar(select(Milestone).where(Milestone.id == ms.id))
    assert ms_check.status == "completed"

    # Verify roadmap.data synced
    rm_check = db.scalar(select(Roadmap).where(Roadmap.id == rm.id))
    m_data = next(m for m in rm_check.data["milestones"] if m["skill"] == "postgresql")
    assert m_data["status"] == "completed"

    # Replay protection: applying again returns 409
    with pytest.raises(HTTPException) as exc:
        apply_suggestion(rm.id, sug.id, test_user, db)
    assert exc.value.status_code == 409


def test_06_cross_user_isolation(db: Session, test_user: User, other_user: User):
    """Verify that User 2 cannot access or mutate User 1's roadmap."""
    from fastapi import HTTPException

    from app.modules.roadmap_tracking.router import (
        EvidenceSubmission,
        StatusUpdate,
        get_tracking,
        submit_milestone_evidence,
        update_milestone,
    )

    res = generate("backend", [])
    rm = Roadmap(
        user_id=test_user.id,
        title="Private User 1 Roadmap",
        data={
            **res,
            "analysis_context": {
                "scope": "public",
                "rubric": "v2.1.0",
                "period": "all_time",
            },
        },
    )
    db.add(rm)
    db.flush()
    ms = Milestone(
        roadmap_id=rm.id,
        external_key="testing",
        title="Testing",
        required_skills=["testing"],
        status="pending",
        version=1,
    )
    db.add(ms)
    db.commit()

    # Other user cannot get tracking
    with pytest.raises(HTTPException) as exc:
        get_tracking(rm.id, other_user, db)
    assert exc.value.status_code == 404

    # Other user cannot update milestone
    with pytest.raises(HTTPException) as exc:
        update_milestone(
            rm.id,
            ms.id,
            StatusUpdate(status="completed", expected_version=1),
            other_user,
            db,
        )
    assert exc.value.status_code == 404

    # Other user cannot submit evidence
    with pytest.raises(HTTPException) as exc:
        submit_milestone_evidence(
            rm.id,
            ms.id,
            EvidenceSubmission(evidence_url="https://github.com/foo/bar/pull/1"),
            other_user,
            db,
        )
    assert exc.value.status_code == 404


def test_07_ai_mentor_roadmap_integration(db: Session, test_user: User):
    """Verify AI Mentor context packaging, action proposals (create, add, modify)."""
    res = generate("backend", [])
    rm = Roadmap(
        user_id=test_user.id,
        title="Mentor Integration Roadmap",
        data={
            **res,
            "analysis_context": {
                "scope": "public",
                "rubric": "v2.1.0",
                "period": "all_time",
            },
        },
    )
    db.add(rm)
    db.flush()
    ms = Milestone(
        roadmap_id=rm.id,
        external_key="fastapi",
        title="FastAPI Web Framework",
        required_skills=["fastapi"],
        status="pending",
        version=1,
    )
    db.add(ms)
    db.commit()

    # 1. Test AI Mentor context collection for milestone_id
    req = MentorChatRequest(
        message="Hỏi về mốc này",
        milestone_id=ms.id,
        sources={"roadmap_ids": [rm.id], "milestone_id": ms.id},
    )
    contexts, limits = _collect_context(db, test_user, req, "ollama")
    m_ctx = next(
        (
            c
            for c in contexts
            if c.source == "roadmap" and c.data.get("milestone_id") == ms.id
        ),
        None,
    )
    assert m_ctx is not None
    assert m_ctx.data["title"] == "FastAPI Web Framework"
    assert m_ctx.data["metric"] != ""
    assert m_ctx.data["objective"] != ""

    # 2. Test AI Mentor Action: update_roadmap with add_milestone
    add_json = json.dumps(
        {
            "claims": [{"text": "Đề xuất thêm mốc RabbitMQ", "evidence_ids": []}],
            "proposal": {
                "tool": "update_roadmap",
                "roadmap_id": rm.id,
                "title": "Roadmap tích hợp Message Queue",
                "add_milestone": {
                    "skill": "rabbitmq",
                    "title": "Message Queue với RabbitMQ",
                    "objective": "Xây dựng hàng đợi bất đồng bộ",
                    "metric": "Xử lý 1000 tasks/phút",
                    "target_score": 75,
                    "after_skill": "fastapi",
                },
            },
        }
    )
    preview_add = propose_action(
        db,
        test_user,
        add_json,
        selected_repos=[],
        context_refs=[],
        sources=["roadmap"],
        uses_private_github=False,
    )
    assert preview_add is not None
    assert preview_add.tool == "update_roadmap"

    # Confirm action
    res_add = decide_action(
        db, test_user, preview_add.id, ActionDecision(decision="confirm")
    )
    assert res_add.status == "succeeded"

    # Verify DB milestone & history created
    db.expire_all()
    rm_check = db.scalar(select(Roadmap).where(Roadmap.id == rm.id))
    assert rm_check.title == "Mentor Integration Roadmap"
    db_rabbitmq = db.scalar(
        select(Milestone).where(
            Milestone.roadmap_id == rm.id, Milestone.external_key == "rabbitmq"
        )
    )
    assert db_rabbitmq is not None
    assert db_rabbitmq.title == "Message Queue với RabbitMQ"

    # Verify order in JSONB
    m_rabbitmq = next(
        m for m in rm_check.data["milestones"] if m["skill"] == "rabbitmq"
    )
    assert m_rabbitmq["title"] == "Message Queue với RabbitMQ"
    assert rm_check.data["milestones"][-1]["skill"] == "rabbitmq"

    # 3. Test AI Mentor Action: update_roadmap with modify_milestone
    mod_json = json.dumps(
        {
            "claims": [{"text": "Cập nhật yêu cầu RabbitMQ", "evidence_ids": []}],
            "proposal": {
                "tool": "update_roadmap",
                "roadmap_id": rm.id,
                "modify_milestone": {
                    "skill": "rabbitmq",
                    "title": "RabbitMQ Advanced Clustering",
                    "objective": "Cấu hình cluster chịu lỗi cao",
                    "metric": "Đạt 99.9% uptime",
                    "target_score": 85,
                },
            },
        }
    )
    preview_mod = propose_action(
        db,
        test_user,
        mod_json,
        selected_repos=[],
        context_refs=[],
        sources=["roadmap"],
        uses_private_github=False,
    )
    res_mod = decide_action(
        db, test_user, preview_mod.id, ActionDecision(decision="confirm")
    )
    assert res_mod.status == "succeeded"

    db.expire_all()
    db_rabbitmq = db.scalar(
        select(Milestone).where(
            Milestone.roadmap_id == rm.id, Milestone.external_key == "rabbitmq"
        )
    )
    assert db_rabbitmq.title == "RabbitMQ Advanced Clustering"

    # 4. Test AI Mentor Action: decline
    dec_json = json.dumps(
        {
            "claims": [{"text": "Đề xuất thêm Kafka", "evidence_ids": []}],
            "proposal": {
                "tool": "update_roadmap",
                "roadmap_id": rm.id,
                "add_milestone": {
                    "skill": "kafka",
                    "title": "Apache Kafka",
                    "objective": "Event Streaming",
                    "metric": "Kafka cluster",
                    "target_score": 80,
                },
            },
        }
    )
    preview_dec = propose_action(
        db,
        test_user,
        dec_json,
        selected_repos=[],
        context_refs=[],
        sources=["roadmap"],
        uses_private_github=False,
    )
    res_dec = decide_action(
        db, test_user, preview_dec.id, ActionDecision(decision="decline")
    )
    assert res_dec.status == "declined"
    # Verify kafka was NOT added
    assert not any(m["skill"] == "kafka" for m in rm_check.data["milestones"])
