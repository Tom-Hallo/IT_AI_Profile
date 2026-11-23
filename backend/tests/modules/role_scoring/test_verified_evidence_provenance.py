"""Role score snapshots must refer to real, owner-verified GitHub events."""

from sqlalchemy import select

from app.modules.analysis.models import RepositoryVerification, VerificationEvidence
from app.modules.role_scoring.schemas import EvidenceRefOut
from app.modules.role_scoring.skill_adapter import DatabaseSkillSnapshotSource
from app.modules.scoring.models import RubricVersion, SkillScore


def test_verified_pr_only_skill_is_available_in_both_role_scopes(db, world):
    user = world.user("verified-pr-role@example.test")
    repo = world.repo(user)
    world.verification(user, repo)
    report = world.report(repo, [])
    verification = db.scalar(
        select(RepositoryVerification).where(
            RepositoryVerification.repository_id == repo.id
        )
    )
    verification.report_id = report.id
    pr = VerificationEvidence(
        verification_id=verification.id,
        repository_id=repo.id,
        user_id=user.id,
        evidence_type="pull_request",
        target_identifier="42",
        verification_status="verified",
        rationale="Authenticated PR creator",
    )
    db.add(pr)
    db.flush()

    rubric = RubricVersion(kind="framework", version="2.2.0", criteria={"weights": {}})
    db.add(rubric)
    db.flush()
    db.add(
        SkillScore(
            user_id=user.id,
            repository_id=repo.id,
            report_id=report.id,
            rubric_id=rubric.id,
            commit_sha=report.commit_sha,
            kind="framework",
            technology="FastAPI",
            status="Scored",
            score=51,
            breakdown=[
                {
                    "criterion": "confidence",
                    "normalized_value": 0.6,
                    "evidence_kind": "verification",
                    "evidence_ids": [pr.id],
                }
            ],
            explanation="Verified PR with source-file evidence",
        )
    )
    db.commit()

    for ids in (None, frozenset({repo.id})):
        raw = DatabaseSkillSnapshotSource(db, repo_id_filter=ids).fetch(user.id)
        assert raw is not None
        item = raw.payload.items[0]
        assert item.status.value == "SCORED"
        assert item.score == 51
        assert item.confidence == 60
        assert len(item.evidence_refs) == 1
        ref = item.evidence_refs[0]
        assert ref.verified is True
        assert ref.finding_type == "pull_request"
        assert ref.pr_number == 42
        assert EvidenceRefOut.from_ref(ref).pr_number == 42
        assert ref.evidence_id == f"verification:{pr.id}"


def test_pr_number_is_not_assumed_from_database_row_id():
    from app.ai.scoring import EvidenceRef

    ref = EvidenceRef(evidence_id="verification:998", finding_type="pull_request")
    assert ref.pr_number is None
    assert EvidenceRefOut.from_ref(ref).pr_number is None


def test_unlinked_scored_row_never_creates_a_fake_evidence_reference(db, world):
    user = world.user("unlinked-role@example.test")
    repo = world.repo(user)
    report = world.report(repo, [])
    rubric = RubricVersion(kind="language", version="1.0.0", criteria={"weights": {}})
    db.add(rubric)
    db.flush()
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
            score=100,
            breakdown=[],
            explanation="Historical score without a verified event",
        )
    )
    db.commit()
    for ids in (None, frozenset({repo.id})):
        raw = DatabaseSkillSnapshotSource(db, repo_id_filter=ids).fetch(user.id)
        assert raw is not None
        item = raw.payload.items[0]
        assert item.status.value == "INSUFFICIENT"
        assert item.score is None
        assert item.confidence is None
        assert item.evidence_refs == []
