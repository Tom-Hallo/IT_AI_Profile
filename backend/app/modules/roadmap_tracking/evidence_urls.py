"""Validate GitHub Commit / Pull Request evidence URLs before persistence.

A syntactically valid URL is not proof of authorship. Verification must still
come from matching stored VerificationEvidence rows.
"""

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

_PATH = re.compile(
    r"^/(?P<owner>[A-Za-z0-9][A-Za-z0-9-]{0,38})"
    r"/(?P<repo>[A-Za-z0-9_.-]+)"
    r"/(?P<kind>commit|pull)"
    r"/(?P<identifier>[A-Za-z0-9]+)/?$"
)
_COMMIT_SHA = re.compile(r"[a-fA-F0-9]{40}\Z")
_PULL_NUMBER = re.compile(r"[1-9][0-9]*\Z")
_ERROR = (
    "Link minh chứng không hợp lệ. Chỉ chấp nhận URL HTTPS chính thức "
    "dẫn trực tiếp đến Commit hoặc Pull Request trên github.com "
    "(ví dụ: https://github.com/owner/repo/pull/123)."
)


@dataclass(frozen=True)
class GitHubEvidenceLink:
    repo_name: str
    evidence_type: Literal["commit", "pull_request"]
    identifier: str


def parse_github_evidence_url(value: str) -> GitHubEvidenceLink:
    """Fail closed for non-GitHub hosts, Issues, repo pages and malformed IDs."""
    value = value.strip()
    if any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ValueError(_ERROR)
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError(_ERROR) from exc
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
    ):
        raise ValueError(_ERROR)
    match = _PATH.fullmatch(parsed.path)
    if match is None or match["repo"] in {".", ".."}:
        raise ValueError(_ERROR)
    kind, identifier = match["kind"], match["identifier"]
    if kind == "commit" and not _COMMIT_SHA.fullmatch(identifier):
        raise ValueError(_ERROR)
    if kind == "pull" and not _PULL_NUMBER.fullmatch(identifier):
        raise ValueError(_ERROR)
    return GitHubEvidenceLink(
        repo_name=f"{match['owner']}/{match['repo']}",
        evidence_type="commit" if kind == "commit" else "pull_request",
        identifier=identifier.lower() if kind == "commit" else identifier,
    )
