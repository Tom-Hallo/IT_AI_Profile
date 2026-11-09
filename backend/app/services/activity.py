"""PBI-010 live GitHub activity: never fabricate historical code snapshots."""

from datetime import UTC, datetime
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


def _timestamp(value: str) -> datetime:
    """Safe ISO 8601 parser supporting trailing Z and preserving timezone awareness."""
    if not value:
        raise ValueError("Empty timestamp string")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def _collect(
    client: GitHubApiClient, endpoint: str, params: dict, max_pages: int = 10
) -> list:
    """Collect paginated items up to max_pages."""
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


async def _collect_pull_requests_in_range(
    client: GitHubApiClient,
    path: str,
    start: datetime,
    end: datetime,
    max_pages: int = 10,
) -> int:
    """Collect PRs created in [start, end) range, terminating pagination when created_at < start."""
    count = 0
    for page in range(1, max_pages + 1):
        response = await client._request(
            "GET",
            f"{path}/pulls",
            {
                "state": "all",
                "sort": "created",
                "direction": "desc",
                "page": page,
                "per_page": 100,
            },
        )
        batch = response.json()
        if not isinstance(batch, list):
            raise HTTPException(502, "Unexpected GitHub response")
        if not batch:
            return count

        reached_earlier_history = False
        for pr in batch:
            created_str = pr.get("created_at")
            if not created_str:
                continue
            created_dt = _timestamp(created_str)
            if created_dt >= end:
                continue
            if created_dt < start:
                reached_earlier_history = True
                break
            count += 1

        if reached_earlier_history or len(batch) < 100:
            return count

    raise HTTPException(413, "Too many records; choose a shorter time window")


async def analyze(
    db: Session, repository_id: int, user_id: int, start: datetime, end: datetime
):
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

    token, scopes = get_user_github_token(db, user_id)
    if not token:
        raise HTTPException(401, "Connect your GitHub account")

    if repo.private:
        has_repo_scope = bool(
            scopes and "repo" in set((scopes or "").replace(",", " ").split())
        )
        if not has_repo_scope:
            raise HTTPException(
                403,
                "Private repository analysis requires 'repo' OAuth scope consent",
            )

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
        filtered_commits = []
        for c in commits:
            commit_meta = c.get("commit") or {}
            committer_date = (commit_meta.get("committer") or {}).get("date")
            author_date = (commit_meta.get("author") or {}).get("date")
            target_date_str = committer_date or author_date
            if target_date_str:
                commit_dt = _timestamp(target_date_str)
                if start <= commit_dt < end:
                    filtered_commits.append(c)

        if len(filtered_commits) > 100:
            raise HTTPException(413, "Over 100 commits; use a shorter window")

        additions = deletions = 0
        for commit in filtered_commits:
            sha = commit.get("sha", "")
            if len(sha) != 40 or any(
                ch not in "0123456789abcdef" for ch in sha.lower()
            ):
                raise HTTPException(502, "Invalid GitHub commit SHA")
            details = (await client._request("GET", f"{path}/commits/{sha}")).json()
            stats = details.get("stats") or {}
            additions += int(stats.get("additions", 0))
            deletions += int(stats.get("deletions", 0))

        pr_count = await _collect_pull_requests_in_range(client, path, start, end)

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
            "commits": len(filtered_commits),
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
