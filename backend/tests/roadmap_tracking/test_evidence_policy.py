"""Regression tests for evidence relevance, target and current visibility."""

from app.modules.roadmap_tracking.evidence_policy import (
    link_key,
    matching_evidence,
    visible_milestone,
)
from app.modules.roadmap_tracking.evidence_urls import parse_github_evidence_url

PR = "https://github.com/Owner/Repo/pull/12"
SHA = "a" * 40


def assessment(skill="python", score=80, repository_id=1):
    return {
        "skill": skill,
        "score": score,
        "confidence": "high",
        "evidence": [
            {
                "id": "verification:12",
                "repository_id": repository_id,
                "finding_type": "pull_request",
                "pr_number": 12,
            },
            {
                "id": "verification-commit:" + SHA,
                "repository_id": repository_id,
                "finding_type": "commit",
                "commit_sha": SHA,
            },
        ],
    }


def test_exact_contribution_and_target_required():
    link = parse_github_evidence_url(PR)
    assert matching_evidence(link, 1, ["Python"], 75, [assessment()])
    assert not matching_evidence(link, 1, ["postgresql"], 75, [assessment()])
    assert not matching_evidence(link, 1, ["python"], 81, [assessment()])
    assert not matching_evidence(link, 2, ["python"], 75, [assessment()])
    assert not matching_evidence(link, 1, ["python"], None, [assessment()])
    assert not matching_evidence(link, 1, ["python", "docker"], 75, [assessment()])


def test_commit_requires_contribution_reference_not_static_analysis():
    link = parse_github_evidence_url(f"https://github.com/Owner/Repo/commit/{SHA}")
    row = assessment()
    assert matching_evidence(link, 1, ["python"], 75, [row])
    row["evidence"][1]["finding_type"] = "source_code"
    assert not matching_evidence(link, 1, ["python"], 75, [row])


def test_canonical_link_key_deduplicates_case_and_trailing_slash():
    assert link_key(PR) == link_key("https://github.com/owner/repo/pull/12/")
    assert link_key(PR) != link_key("https://github.com/owner/repo/pull/13")


def test_revoked_evidence_is_hidden_and_badge_invalidated():
    original = {
        "skill": "python",
        "target_score": 75,
        "gap_type": "skill_gap",
        "current_score": 80,
        "evidence": [
            {
                "source": "submission",
                "repository_id": 1,
                "url": PR,
                "verified": True,
                "verification_status": "verified",
            }
        ],
        "verification_status": "verified",
        "evaluation_evidence": [{"skill": "python", "ref": "verification:12"}],
    }
    visible = visible_milestone(original, set(), [])
    assert visible["evidence"] == []
    assert visible["evaluation_evidence"] == []
    assert visible["verification_status"] == "pending"
    assert visible["current_score"] is None
    assert original["evidence"][0]["verified"] is True


def test_old_verified_submission_downgrades_without_matching_current_skill():
    original = {
        "skill": "postgresql",
        "target_score": 75,
        "evidence": [
            {
                "repository_id": 1,
                "source": "submission",
                "url": PR,
                "verified": True,
                "verification_status": "verified",
            }
        ],
    }
    visible = visible_milestone(original, {1}, [assessment()])
    assert visible["evidence"][0]["verification_status"] == "self_reported"
    assert visible["evidence"][0]["verified"] is False
