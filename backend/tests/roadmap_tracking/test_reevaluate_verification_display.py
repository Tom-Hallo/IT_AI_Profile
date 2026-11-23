"""Regression: manually completed milestones are not labeled Git Verified."""

from app.modules.roadmap_tracking.models import Milestone
from app.modules.roadmap_tracking.router import serialize_milestone


def milestone():
    return Milestone(
        id=15,
        roadmap_id=1,
        external_key="python",
        title="Python",
        required_skills=["python"],
        status="completed",
        version=2,
    )


def test_manual_completed_milestone_is_not_git_verified():
    result = serialize_milestone(milestone(), {"skill": "python", "evidence": []})
    assert result["verification_status"] == "pending"


def test_unverified_issue_link_is_never_git_verified():
    result = serialize_milestone(
        milestone(),
        {
            "skill": "python",
            "evidence": [
                {
                    "url": "https://github.com/owner/repo/issues/1",
                    "verified": False,
                    "verification_status": "self_reported",
                }
            ],
        },
    )
    assert result["verification_status"] == "self_reported"


def test_verified_submission_can_show_verified_badge():
    result = serialize_milestone(
        milestone(),
        {
            "skill": "python",
            "evidence": [
                {
                    "url": "https://github.com/owner/repo/pull/12",
                    "verified": True,
                    "verification_status": "verified",
                }
            ],
        },
    )
    assert result["verification_status"] == "verified"


def test_verified_reevaluation_evidence_can_show_verified_badge():
    result = serialize_milestone(
        milestone(),
        {
            "skill": "python",
            "verification_status": "verified",
            "evaluation_evidence": [{"skill": "python", "ref": "record:1"}],
        },
    )
    assert result["verification_status"] == "verified"
