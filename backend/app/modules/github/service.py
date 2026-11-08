"""Dịch vụ đồng bộ GitHub Repositories (PBI-009).

Quy tắc:
- Idempotent upsert: đồng bộ nhiều lần không tạo bản ghi trùng lặp.
- Định danh duy nhất theo external_id (GitHub repo ID), không dựa theo tên repo.
- Bảo toàn quan hệ nhiều-nhiều qua bảng user_repository.
- Không xóa nhầm dữ liệu lịch sử khi sync bị gián đoạn hoặc API lỗi giữa chừng.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from dateutil.parser import isoparse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.redis import get_redis_connection
from app.modules.auth.service import get_user_github_token
from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository, user_repository
from app.modules.users.models import User

logger = logging.getLogger(__name__)

SYNC_STATUS_PREFIX = "ita:github:sync:"
SYNC_STATUS_TTL_SECONDS = 86400  # 24 giờ


def _parse_iso(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        dt = isoparse(val)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return None


def get_sync_status_cache(user_id: int) -> dict[str, Any] | None:
    """Đọc trạng thái đồng bộ gần nhất từ Redis."""
    try:
        redis = get_redis_connection()
        raw = redis.get(f"{SYNC_STATUS_PREFIX}{user_id}")
        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
    except Exception:
        logger.warning(f"Không thể đọc sync status cache từ Redis cho user_id={user_id}")
    return None


def set_sync_status_cache(
    user_id: int,
    status: str,
    total_synced: int = 0,
    last_synced_at: str | None = None,
    error_message: str | None = None,
) -> None:
    """Lưu trạng thái đồng bộ vào Redis."""
    try:
        redis = get_redis_connection()
        data = {
            "status": status,
            "total_synced": total_synced,
            "last_synced_at": last_synced_at,
            "error_message": error_message,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        redis.set(
            f"{SYNC_STATUS_PREFIX}{user_id}",
            json.dumps(data),
            ex=SYNC_STATUS_TTL_SECONDS,
        )
    except Exception:
        logger.warning(f"Không thể ghi sync status cache vào Redis cho user_id={user_id}")


def get_user_sync_status(db: Session, user_id: int) -> dict[str, Any]:
    """Lấy trạng thái tổng hợp của tiến trình đồng bộ GitHub cho user."""
    token, scope = get_user_github_token(db, user_id)
    is_connected = token is not None
    has_private_scope = bool(scope and "repo" in scope)

    # Đếm số repositories hiện có trong DB của user
    count_stmt = (
        select(func.count(Repository.id))
        .select_from(Repository)
        .join(
            user_repository,
            Repository.id == user_repository.c.repository_id,
        )
        .where(user_repository.c.user_id == user_id)
    )
    total_repos = db.scalar(count_stmt) or 0

    # Lấy thời điểm đồng bộ gần nhất từ DB
    max_sync_stmt = (
        select(func.max(Repository.last_synced_at))
        .select_from(Repository)
        .join(
            user_repository,
            Repository.id == user_repository.c.repository_id,
        )
        .where(user_repository.c.user_id == user_id)
    )
    last_synced_dt: datetime | None = db.scalar(max_sync_stmt)
    last_synced_at = last_synced_dt.isoformat() if last_synced_dt else None

    # Đọc cache Redis nếu đang chạy hoặc có lỗi
    cached = get_sync_status_cache(user_id)
    status = "idle"
    error_message = None

    if cached:
        status = cached.get("status", "idle")
        error_message = cached.get("error_message")
        if cached.get("last_synced_at"):
            last_synced_at = cached.get("last_synced_at")

    return {
        "status": status,
        "is_connected": is_connected,
        "has_private_scope": has_private_scope,
        "total_repositories": total_repos,
        "last_synced_at": last_synced_at,
        "error_message": error_message,
    }


async def sync_repositories_for_user(
    db: Session,
    user: User,
    client: GitHubApiClient | None = None,
) -> dict[str, Any]:
    """Thực hiện đồng bộ repositories từ GitHub API vào PostgreSQL.

    Thực hiện transactional: đảm bảo tính toàn vẹn dữ liệu.
    """
    if client is None:
        token, _ = get_user_github_token(db, user.id)
        if not token:
            raise GitHubTokenRevokedError("Chưa kết nối GitHub hoặc token đã hết hạn.")
        client = GitHubApiClient(token)

    set_sync_status_cache(user.id, status="running")

    try:
        repos_data = await client.list_repositories()
        sync_timestamp = datetime.now(UTC)

        for repo in repos_data:
            external_id = str(repo["id"])
            name = repo.get("name") or "unknown"
            full_name = repo.get("full_name") or name
            html_url = repo.get("html_url") or f"https://github.com/{full_name}"
            description = repo.get("description")
            private = bool(repo.get("private", False))
            default_branch = repo.get("default_branch") or "main"
            is_fork = bool(repo.get("fork", False))

            fork_source = None
            if is_fork:
                if "parent" in repo and isinstance(repo["parent"], dict):
                    fork_source = repo["parent"].get("full_name")
                else:
                    owner_info = repo.get("owner")
                    owner_login = owner_info.get("login") if isinstance(owner_info, dict) else None
                    if owner_login and name:
                        try:
                            details = await client.get_repository_details(owner_login, name)
                            if "parent" in details and isinstance(details["parent"], dict):
                                fork_source = details["parent"].get("full_name")
                        except Exception:
                            pass

            owner_info = repo.get("owner")
            owner_login = owner_info.get("login") if isinstance(owner_info, dict) else None
            languages: dict[str, int] = {}
            if owner_login and name:
                try:
                    languages = await client.get_repository_languages(owner_login, name)
                except Exception:
                    languages = {}

            primary_language = repo.get("language")
            if not primary_language and languages:
                primary_language = max(languages, key=languages.get)

            stars_count = int(repo.get("stargazers_count", 0))
            forks_count = int(repo.get("forks_count", 0))
            open_issues_count = int(repo.get("open_issues_count", 0))
            size_kb = int(repo.get("size", 0))
            archived = bool(repo.get("archived", False))
            disabled = bool(repo.get("disabled", False))

            github_created_at = _parse_iso(repo.get("created_at"))
            github_updated_at = _parse_iso(repo.get("updated_at"))
            pushed_at = _parse_iso(repo.get("pushed_at"))

            # 1. Tìm hoặc tạo Repository theo external_id
            existing = db.scalar(select(Repository).where(Repository.external_id == external_id))

            if existing is not None:
                existing.name = name
                existing.full_name = full_name
                existing.html_url = html_url
                existing.description = description
                existing.private = private
                existing.default_branch = default_branch
                existing.is_fork = is_fork
                existing.fork_source = fork_source
                existing.languages = languages
                existing.primary_language = primary_language
                existing.stars_count = stars_count
                existing.forks_count = forks_count
                existing.open_issues_count = open_issues_count
                existing.size_kb = size_kb
                existing.archived = archived
                existing.disabled = disabled
                existing.github_created_at = github_created_at
                existing.github_updated_at = github_updated_at
                existing.pushed_at = pushed_at
                existing.last_synced_at = sync_timestamp
                existing.sync_status = "synced"
                existing.updated_at = func.now()
                repo_record = existing
            else:
                repo_record = Repository(
                    owner_id=user.id,
                    external_id=external_id,
                    name=name,
                    full_name=full_name,
                    html_url=html_url,
                    description=description,
                    private=private,
                    default_branch=default_branch,
                    is_fork=is_fork,
                    fork_source=fork_source,
                    languages=languages,
                    primary_language=primary_language,
                    stars_count=stars_count,
                    forks_count=forks_count,
                    open_issues_count=open_issues_count,
                    size_kb=size_kb,
                    archived=archived,
                    disabled=disabled,
                    github_created_at=github_created_at,
                    github_updated_at=github_updated_at,
                    pushed_at=pushed_at,
                    last_synced_at=sync_timestamp,
                    sync_status="synced",
                )
                db.add(repo_record)
                db.flush()

            # 2. Đảm bảo liên kết trong bảng pivot user_repository
            pivot_exists = db.scalar(
                select(1)
                .select_from(user_repository)
                .where(
                    user_repository.c.user_id == user.id,
                    user_repository.c.repository_id == repo_record.id,
                )
            )
            if not pivot_exists:
                db.execute(
                    user_repository.insert().values(
                        user_id=user.id,
                        repository_id=repo_record.id,
                        added_at=sync_timestamp,
                    )
                )

        db.commit()

        set_sync_status_cache(
            user.id,
            status="completed",
            total_synced=len(repos_data),
            last_synced_at=sync_timestamp.isoformat(),
        )

        return {
            "status": "completed",
            "synced_count": len(repos_data),
            "last_synced_at": sync_timestamp.isoformat(),
        }

    except (GitHubRateLimitError, GitHubTokenRevokedError, GitHubApiError) as exc:
        db.rollback()
        set_sync_status_cache(
            user.id,
            status="failed",
            error_message=str(exc),
        )
        raise

    except Exception as exc:
        db.rollback()
        logger.exception("Lỗi không mong muốn khi đồng bộ repositories")
        set_sync_status_cache(
            user.id,
            status="failed",
            error_message="Lỗi máy chủ nội bộ trong quá trình đồng bộ.",
        )
        raise GitHubApiError("Đồng bộ repository thất bại do lỗi hệ thống.") from exc
