"""PBI-010 live GitHub activity: never fabricate historical code snapshots."""

from datetime import datetime
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.service import get_user_github_token
from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository, user_repository


async def _collect(client, endpoint, params, max_pages=10):
    records = []
    for page in range(1, max_pages + 1):
        response = await client._request(
            "GET", endpoint, {**params, "page": page, "per_page": 100}
        )
        batch = response.json()
        if not isinstance(batch, list):
            raise HTTPException(502, "Unexpected GitHub response")
        records.extend(batch)
        if len(batch) < 100:
            return records
    raise HTTPException(413, "Too many records; choose a shorter time window")


def _timestamp(value):
    return datetime.fromisoformat(value)


async def analyze(db: Session, repository_id: int, user_id: int, start, end):
    repo = db.scalar(
        select(Repository)
        .join(user_repository, Repository.id == user_repository.c.repository_id)
        .where(
            Repository.id == repository_id,
            user_repository.c.user_id == user_id,
        )
    )
    if repo is None:
        raise HTTPException(404, "Repository not found or access denied")
    if repo.last_synced_at is None or repo.sync_status != "synced":
        raise HTTPException(409, "Repository sync is incomplete")
    token, _ = get_user_github_token(db, user_id)
    if not token:
        raise HTTPException(401, "Connect your GitHub account")
    if not repo.full_name or len(repo.full_name.split("/")) != 2:
        raise HTTPException(422, "Invalid repository full name")

    owner, name = repo.full_name.split("/")
    path = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
    client = GitHubApiClient(token)
    try:
        commits = await _collect(
            client,
            f"{path}/commits",
            {"since": start.isoformat(), "until": end.isoformat()},
        )
        commits = [
            c
            for c in commits
            if (c.get("commit") or {}).get("committer", {}).get("date")
            and start <= _timestamp(c["commit"]["committer"]["date"]) < end
        ]
        if len(commits) > 100:
            raise HTTPException(413, "Over 100 commits; use a shorter window")
        additions = deletions = 0
        for commit in commits:
            sha = commit.get("sha", "")
            if len(sha) != 40 or any(
                ch not in "0123456789abcdef" for ch in sha.lower()
            ):
                raise HTTPException(502, "Invalid GitHub commit SHA")
            details = (await client._request("GET", f"{path}/commits/{sha}")).json()
            stats = details.get("stats") or {}
            additions += int(stats.get("additions", 0))
            deletions += int(stats.get("deletions", 0))
        prs = await _collect(
            client,
            f"{path}/pulls",
            {"state": "all", "sort": "created", "direction": "desc"},
        )
        pr_count = sum(
            start <= _timestamp(p["created_at"]) < end
            for p in prs
            if p.get("created_at")
        )
    except GitHubTokenRevokedError as exc:
        raise HTTPException(401, str(exc)) from None
    except GitHubPermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    except GitHubNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except GitHubRateLimitError as exc:
        raise HTTPException(429, str(exc)) from None
    except GitHubApiError as exc:
        raise HTTPException(502, str(exc)) from None

    return {
        "repository_id": repository_id,
        "period": {
            "start_utc": start.isoformat(),
            "end_exclusive_utc": end.isoformat(),
        },
        "activity": {
            "commits": len(commits),
            "pull_requests_created": pr_count,
            "additions": additions,
            "deletions": deletions,
        },
        "base_code": {
            "status": "unavailable",
            "lines": None,
            "as_of_utc": None,
        },
        "sync": {
            "last_synced_at": repo.last_synced_at.isoformat(),
            "complete_through_end": False,
        },
        "source": "github_live",
        "limitations": [
            "Historical code baseline is unavailable until snapshots are collected.",
            "Repository activity is not a per-user contribution score.",
            "Metadata sync does not guarantee complete historical activity coverage.",
        ],
    }
