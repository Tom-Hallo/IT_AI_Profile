"""Regression tests for the production roadmap evidence URL parser and API.

All invalid cases must fail before any database write.
"""

import pytest
from fastapi import HTTPException

from app.modules.roadmap_tracking.evidence_urls import parse_github_evidence_url
from app.modules.roadmap_tracking.router import (
    EvidenceSubmission,
    submit_milestone_evidence,
)

VALID_SHA = "a" * 40


@pytest.mark.parametrize(
    ("url", "kind", "identifier"),
    [
        ("https://github.com/Tom-Hallo/IT_AI_Profile/pull/98", "pull_request", "98"),
        (
            f"https://github.com/Tom-Hallo/IT_AI_Profile/commit/{VALID_SHA}",
            "commit",
            VALID_SHA,
        ),
    ],
)
def test_official_commit_and_pr_links_parse(url, kind, identifier):
    result = parse_github_evidence_url(url)
    assert result.repo_name == "Tom-Hallo/IT_AI_Profile"
    assert result.evidence_type == kind
    assert result.identifier == identifier


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/Tom-Hallo/IT_AI_Profile/issues/1",
        "https://github.com.attacker.com/repo/commit/12345",
        "https://github.com/Tom-Hallo/IT_AI_Profile",
        "https://github.com/Tom-Hallo/IT_AI_Profile/pull/0",
        "https://github.com/Tom-Hallo/IT_AI_Profile/pull/nope",
        "https://github.com/Tom-Hallo/IT_AI_Profile/commit/12345",
        "http://github.com/Tom-Hallo/IT_AI_Profile/pull/98",
        "https://github.com/Tom-Hallo/IT_AI_Profile/pull/98?x=1",
        "https://github.com/Tom-Hallo/IT_AI_Profile/pull/98#conversation",
        "https://github.com@attacker.com/Tom-Hallo/IT_AI_Profile/pull/98",
        "https://github.com:443/Tom-Hallo/IT_AI_Profile/pull/98",
        "https://github.com/Tom-Hallo/IT_AI_Profile/pull/98/files",
        "https://github.com/Tom-Hallo/IT_AI_Profile/commit/",
        "https://gitlab.com/Tom-Hallo/IT_AI_Profile/pull/98",
    ],
)
def test_invalid_links_are_rejected_before_any_db_access(url):
    with pytest.raises(ValueError):
        parse_github_evidence_url(url)

    # Even without a working DB object, malformed URLs must return HTTP 422.
    with pytest.raises(HTTPException) as exc:
        submit_milestone_evidence(
            roadmap_id=1,
            milestone_id=2,
            payload=EvidenceSubmission(evidence_url=url),
            user=object(),
            db=object(),
        )
    assert exc.value.status_code == 422
    assert "Commit" in exc.value.detail
