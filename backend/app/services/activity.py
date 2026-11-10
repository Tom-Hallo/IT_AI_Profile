"""PBI-010 live GitHub activity: personal contributions vs repository context."""

import asyncio
from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import OAuthAccount
from app.modules.auth.service import get_user_github_token
from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
    GitHubEmptyRepositoryError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository, user_repository

MAX_COMMITS_FOR_ANALYSIS = 1000
DEFAULT_CONCURRENCY = 10


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
    client: GitHubApiClient, endpoint: str, params: dict, max_pages: int = 50
) -> list:
    """Collect paginated items up to max_pages."""
    records = []
    for page in range(1, max_pages + 1):
        try:
            response = await client._request(
                "GET", endpoint, {**params, "page": page, "per_page": 100}
            )
        except GitHubEmptyRepositoryError:
            return []
        batch = response.json()
        if not isinstance(batch, list):
            raise HTTPException(502, "Unexpected GitHub response")
        records.extend(batch)
        if len(batch) < 100:
            return records
    raise HTTPException(
        413,
        f"Khoảng thời gian chứa quá nhiều dữ liệu "
        f"(>{MAX_COMMITS_FOR_ANALYSIS} commits). "
        "Vui lòng chọn khoảng thời gian ngắn hơn.",
    )


async def _collect_pull_requests_list_in_range(
    client: GitHubApiClient,
    path: str,
    start: datetime,
    end: datetime,
    max_pages: int = 50,
) -> list[dict]:
    """Collect PRs created in [start, end) range, terminating pagination when created_at
    < start.
    """
    prs: list[dict] = []
    for page in range(1, max_pages + 1):
        try:
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
        except GitHubEmptyRepositoryError:
            return []
        batch = response.json()
        if not isinstance(batch, list):
            raise HTTPException(502, "Unexpected GitHub response")
        if not batch:
            return prs

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
            prs.append(pr)

        if reached_earlier_history or len(batch) < 100:
            return prs

    raise HTTPException(
        413,
        "Khoảng thời gian chứa quá nhiều dữ liệu (>1000 pull requests). "
        "Vui lòng chọn khoảng thời gian ngắn hơn.",
    )


async def _collect_pull_requests_in_range(
    client: GitHubApiClient,
    path: str,
    start: datetime,
    end: datetime,
    max_pages: int = 50,
) -> int:
    """Collect PRs created in [start, end) range and return count."""
    prs = await _collect_pull_requests_list_in_range(
        client, path, start, end, max_pages
    )
    return len(prs)


async def analyze(
    db: Session,
    repository_id: int,
    user_id: int,
    start: datetime,
    end: datetime,
    scope: Literal["personal", "repository"] = "personal",
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
        from app.modules.auth.service import has_repo_scope

        if not has_repo_scope(scopes):
            raise HTTPException(
                403,
                "Private repository analysis requires 'repo' OAuth scope consent",
            )
        if not has_private_access(db, user_id):
            raise HTTPException(
                403,
                "Private repository analysis requires active private authorization",
            )
        try:
            from app.modules.consent.guards import require_private_access_consent

            require_private_access_consent(db, user_id, repository_id)
        except AttributeError:
            raise HTTPException(403, "Private repository consent required") from None

    if not repo.full_name or len(repo.full_name.split("/")) != 2:
        raise HTTPException(422, "Invalid repository full name")

    oauth_acc = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.user_id == user_id,
            OAuthAccount.provider == "github",
        )
    )
    p_uid = getattr(oauth_acc, "provider_user_id", None)
    auth_github_user_id = str(p_uid) if p_uid is not None else str(user_id)
    auth_github_login: str | None = None

    owner, name = repo.full_name.split("/")
    path = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
    client = GitHubApiClient(token)
    client_ctx = client if hasattr(client, "__aenter__") else nullcontext(client)
    try:
        async with client_ctx:
            # Query authenticated GitHub user profile for username matching
            try:
                user_res = await client._request("GET", "/user")
                user_data = user_res.json()
                if isinstance(user_data, dict):
                    auth_github_login = user_data.get("login")
                    if user_data.get("id"):
                        auth_github_user_id = str(user_data.get("id"))
            except GitHubApiError:
                pass

            commits = await _collect(
                client,
                f"{path}/commits",
                {"since": start.isoformat(), "until": end.isoformat()},
            )
            filtered_commits: list[tuple[dict, str]] = []
            for c in commits:
                commit_meta = c.get("commit") or {}
                committer_date = (commit_meta.get("committer") or {}).get("date")
                author_date = (commit_meta.get("author") or {}).get("date")
                target_date_str = committer_date or author_date
                if target_date_str:
                    commit_dt = _timestamp(target_date_str)
                    if start <= commit_dt < end:
                        filtered_commits.append((c, target_date_str))

            if len(filtered_commits) > MAX_COMMITS_FOR_ANALYSIS:
                raise HTTPException(
                    413,
                    f"Khoảng thời gian chứa quá nhiều dữ liệu "
                    f"(>{MAX_COMMITS_FOR_ANALYSIS} commits). "
                    "Vui lòng chọn khoảng thời gian ngắn hơn.",
                )

            sem = asyncio.Semaphore(DEFAULT_CONCURRENCY)

            async def _fetch_commit_details(item: tuple[dict, str]) -> dict:
                c, target_date_str = item
                sha = c.get("sha", "")
                if len(sha) != 40 or any(
                    ch not in "0123456789abcdef" for ch in sha.lower()
                ):
                    raise HTTPException(502, "Invalid GitHub commit SHA")
                async with sem:
                    details = (
                        await client._request("GET", f"{path}/commits/{sha}")
                    ).json()
                    stats = details.get("stats") or {}
                    additions = int(stats.get("additions", 0))
                    deletions = int(stats.get("deletions", 0))

                    author_obj = c.get("author") or details.get("author")
                    author_id = (
                        str(author_obj.get("id"))
                        if isinstance(author_obj, dict) and author_obj.get("id")
                        else None
                    )
                    author_login = (
                        author_obj.get("login", "")
                        if isinstance(author_obj, dict)
                        else ""
                    )
                    author_type = (
                        author_obj.get("type", "User")
                        if isinstance(author_obj, dict)
                        else "User"
                    )

                    commit_author_name = (
                        (c.get("commit") or {}).get("author") or {}
                    ).get("name", "")
                    is_bot = (
                        author_type.lower() == "bot"
                        or "[bot]" in author_login.lower()
                        or "[bot]" in commit_author_name.lower()
                    )

                    id_match = bool(
                        auth_github_user_id
                        and author_id
                        and author_id == str(auth_github_user_id)
                    )
                    login_match = bool(
                        auth_github_login
                        and author_login
                        and author_login.lower() == auth_github_login.lower()
                    )
                    is_verified = (id_match or login_match) and not is_bot
                    is_merge = len(c.get("parents", [])) > 1

                    return {
                        "sha": sha,
                        "html_url": c.get("html_url")
                        or f"https://github.com/{repo.full_name}/commit/{sha}",
                        "message": (c.get("commit") or {})
                        .get("message", "")
                        .split("\n")[0],
                        "committed_at": target_date_str,
                        "additions": additions,
                        "deletions": deletions,
                        "verified_authorship": is_verified,
                        "is_merge": is_merge,
                        "is_bot": is_bot,
                        "author_login": author_login,
                    }

            if filtered_commits:
                commit_records = await asyncio.gather(
                    *[_fetch_commit_details(item) for item in filtered_commits]
                )
            else:
                commit_records = []

            raw_prs = await _collect_pull_requests_list_in_range(
                client, path, start, end
            )
            pr_records: list[dict] = []
            for pr in raw_prs:
                u_info = pr.get("user") or {}
                pr_u_id = (
                    str(u_info.get("id"))
                    if isinstance(u_info, dict) and u_info.get("id")
                    else None
                )
                pr_u_login = u_info.get("login", "") if isinstance(u_info, dict) else ""
                is_p_pr = bool(
                    (
                        auth_github_user_id
                        and pr_u_id
                        and pr_u_id == str(auth_github_user_id)
                    )
                    or (
                        auth_github_login
                        and pr_u_login
                        and pr_u_login.lower() == auth_github_login.lower()
                    )
                )
                pr_records.append(
                    {
                        "number": pr.get("number"),
                        "title": pr.get("title", ""),
                        "html_url": pr.get("html_url", ""),
                        "created_at": pr.get("created_at"),
                        "state": pr.get("state", "open"),
                        "merged": bool(pr.get("merged_at") or pr.get("merged")),
                        "is_personal": is_p_pr,
                        "user_login": pr_u_login,
                    }
                )

            personal_commits = [c for c in commit_records if c["verified_authorship"]]
            personal_prs = [p for p in pr_records if p["is_personal"]]

            personal_additions = sum(c["additions"] for c in personal_commits)
            personal_deletions = sum(c["deletions"] for c in personal_commits)
            personal_merge_count = sum(1 for c in personal_commits if c["is_merge"])

            unverified_count = sum(
                1
                for c in commit_records
                if not c["verified_authorship"] and not c["is_bot"]
            )
            bot_count = sum(1 for c in commit_records if c["is_bot"])

            total_commits = len(commit_records)
            total_prs = len(pr_records)
            total_additions = sum(c["additions"] for c in commit_records)
            total_deletions = sum(c["deletions"] for c in commit_records)
            team_commits = max(0, total_commits - len(personal_commits))

            if scope == "personal":
                activity_metrics = {
                    "commits": len(personal_commits),
                    "pull_requests_created": len(personal_prs),
                    "additions": personal_additions,
                    "deletions": personal_deletions,
                }
                evidence_commits = personal_commits[:100]
                evidence_prs = personal_prs
            else:
                activity_metrics = {
                    "commits": total_commits,
                    "pull_requests_created": total_prs,
                    "additions": total_additions,
                    "deletions": total_deletions,
                }
                evidence_commits = commit_records[:100]
                evidence_prs = pr_records

    except GitHubTokenRevokedError as exc:
        raise HTTPException(401, str(exc)) from None
    except GitHubPermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    except GitHubNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except GitHubRateLimitError as exc:
        raise HTTPException(429, str(exc)) from None
    except GitHubEmptyRepositoryError:
        personal_commits = []
        personal_prs = []
        personal_additions = personal_deletions = 0
        personal_merge_count = unverified_count = bot_count = 0
        total_commits = total_prs = 0
        total_additions = total_deletions = 0
        team_commits = 0
        evidence_commits = []
        evidence_prs = []
        activity_metrics = {
            "commits": 0,
            "pull_requests_created": 0,
            "additions": 0,
            "deletions": 0,
        }
    except GitHubApiError as exc:
        raise HTTPException(502, str(exc)) from None

    return {
        "repository_id": repository_id,
        "scope": scope,
        "period": {
            "start_utc": start.isoformat(),
            "end_exclusive_utc": end.isoformat(),
        },
        "developer": {
            "user_id": user_id,
            "github_user_id": auth_github_user_id,
            "github_login": auth_github_login,
        },
        "activity": activity_metrics,
        "personal_contribution": {
            "commits": len(personal_commits),
            "pull_requests_created": len(personal_prs),
            "additions": personal_additions,
            "deletions": personal_deletions,
            "merge_commits": personal_merge_count,
            "unverified_commits": unverified_count,
            "bot_commits": bot_count,
        },
        "repository_context": {
            "total_commits": total_commits,
            "total_pull_requests_created": total_prs,
            "total_additions": total_additions,
            "total_deletions": total_deletions,
            "team_commits": team_commits,
        },
        "evidence": {
            "commits": evidence_commits,
            "pull_requests": evidence_prs,
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
        "data_completeness": {
            "status": "complete",
            "pr_event_type": "created_at",
            "scope": scope,
            "confidence": "high"
            if len(personal_commits) > 0 or total_commits == 0
            else "medium",
        },
        "limitations": [
            "PR counts reflect pull requests created within the UTC date range.",
            (
                "Personal commits require verified GitHub user ID or login "
                "matching the authenticated account."
            ),
            (
                "Unverified email/name-only commits without linked GitHub account "
                "are excluded from personal contribution."
            ),
            ("Historical code baseline is unavailable until snapshots are collected."),
            (
                "Activity metrics reflect raw contribution volume and do not equate "
                "to developer skill or proficiency."
            ),
        ],
    }
