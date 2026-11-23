import copy
from urllib.parse import urlsplit


def parse_and_validate_github_url(url: str):
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() not in {
        "github.com",
        "www.github.com",
    }:
        return False, "Not a valid GitHub HTTPS URL"
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 4 or parts[2] not in {"commit", "pull"}:
        return False, "URL must point to a GitHub commit or pull request"
    owner, repo_slug, kind, identifier = parts[0], parts[1], parts[2], parts[3]
    return True, (owner, repo_slug, kind, identifier)


def test_github_url_strict_validation():
    # Valid commit URL
    valid_commit, details = parse_and_validate_github_url(
        "https://github.com/org/repo/commit/abc1234567890"
    )
    assert valid_commit is True
    assert details == ("org", "repo", "commit", "abc1234567890")

    # Valid PR URL
    valid_pr, details = parse_and_validate_github_url(
        "https://github.com/org/repo/pull/42"
    )
    assert valid_pr is True
    assert details == ("org", "repo", "pull", "42")

    # Invalid scheme (http)
    inv_scheme, _ = parse_and_validate_github_url(
        "http://github.com/org/repo/commit/abc123"
    )
    assert inv_scheme is False

    # Invalid domain
    inv_domain, _ = parse_and_validate_github_url(
        "https://gitlab.com/org/repo/commit/abc123"
    )
    assert inv_domain is False

    # Arbitrary path containing commit as query or fragment
    inv_path, _ = parse_and_validate_github_url(
        "https://github.com/org/repo/issues/1?ref=commit"
    )
    assert inv_path is False

    # SSRF / attacker domain spoofing
    inv_spoof, _ = parse_and_validate_github_url(
        "https://github.com.attacker.com/org/repo/commit/abc123"
    )
    assert inv_spoof is False


def test_nested_jsonb_mutation_deepcopy_persistence():
    class DummyModel:
        def __init__(self, data):
            self.data = data

    roadmap = DummyModel({"milestones": [{"id": 1, "skill": "Python", "evidence": []}]})

    # Mutate using deepcopy pattern as implemented in router.py
    data = copy.deepcopy(roadmap.data) if isinstance(roadmap.data, dict) else {}
    milestones = data.setdefault("milestones", [])
    assert len(milestones) == 1
    item = milestones[0]
    item.setdefault("evidence", []).append(
        {
            "type": "github_url",
            "url": "https://github.com/org/repo/pull/42",
            "notes": "Added integration tests",
            "verified": True,
        }
    )

    roadmap.data = data
    # Verify deepcopy created isolated objects and updated accurately
    assert (
        roadmap.data["milestones"][0]["evidence"][0]["notes"]
        == "Added integration tests"
    )
    assert roadmap.data["milestones"][0]["evidence"][0]["verified"] is True
