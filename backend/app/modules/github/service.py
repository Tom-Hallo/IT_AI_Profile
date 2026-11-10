"""Dịch vụ đồng bộ GitHub Repositories (PBI-009).

Quy tắc:
- Idempotent upsert: đồng bộ nhiều lần không tạo bản ghi trùng lặp.
- Định danh duy nhất theo external_id (GitHub repo ID), không dựa theo tên repo.
- Bảo toàn quan hệ nhiều-nhiều qua bảng user_repository.
- Không xóa nhầm dữ liệu lịch sử khi sync bị gián đoạn hoặc API lỗi giữa chừng.
- Tối ưu hóa API: Bounded concurrency, HTTP keep-alive, bỏ qua repo rỗng
  hoặc không có commit mới.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from dateutil.parser import ParserError, isoparse
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis import get_redis_connection
from app.modules.analysis.evidence import UTC
from app.modules.auth.service import get_user_github_token, has_private_access
from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
    GitHubNotFoundError,
    GitHubPermissionError,
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
    except (ParserError, ValueError, TypeError, OverflowError):
        return None


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def get_sync_status_cache(user_id: int) -> dict[str, Any] | None:
    """Đọc trạng thái đồng bộ gần nhất từ Redis."""
    try:
        redis = get_redis_connection()
        raw = redis.get(f"{SYNC_STATUS_PREFIX}{user_id}")
        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
    except (RedisError, OSError, UnicodeError, json.JSONDecodeError, TypeError):
        logger.warning(
            f"Không thể đọc sync status cache từ Redis cho user_id={user_id}"
        )
    return None


def set_sync_status_cache(
    user_id: int,
    status: str,
    total_synced: int = 0,
    last_synced_at: str | None = None,
    error_message: str | None = None,
    job_id: str | None = None,
) -> None:
    """Lưu trạng thái đồng bộ vào Redis."""
    try:
        redis = get_redis_connection()
        data = {
            "status": status,
            "total_synced": total_synced,
            "last_synced_at": last_synced_at,
            "error_message": error_message,
            "job_id": job_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        redis.set(
            f"{SYNC_STATUS_PREFIX}{user_id}",
            json.dumps(data),
            ex=SYNC_STATUS_TTL_SECONDS,
        )
    except (RedisError, OSError, UnicodeError, json.JSONDecodeError, TypeError):
        logger.warning(
            f"Không thể ghi sync status cache vào Redis cho user_id={user_id}"
        )


def get_user_sync_status(db: Session, user_id: int) -> dict[str, Any]:
    """Lấy trạng thái tổng hợp của tiến trình đồng bộ GitHub cho user."""
    token, _ = get_user_github_token(db, user_id)
    is_connected = token is not None
    can_access_private = has_private_access(db, user_id)
    has_private_scope = can_access_private

    # Đếm số repositories hiện có trong DB của user thuộc phạm vi được cấp phép
    count_stmt = (
        select(func.count(Repository.id))
        .select_from(Repository)
        .join(
            user_repository,
            Repository.id == user_repository.c.repository_id,
        )
        .where(user_repository.c.user_id == user_id)
    )
    if not can_access_private:
        count_stmt = count_stmt.where(Repository.private.is_(False))

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
    if not can_access_private:
        max_sync_stmt = max_sync_stmt.where(Repository.private.is_(False))

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

        # Nếu trạng thái cache là "running", kiểm tra xem RQ job thực tế còn chạy không
        if status == "running":
            cached_job_id = cached.get("job_id")
            if cached_job_id:
                try:
                    from app.workers.enqueue import fetch_job

                    job = fetch_job(cached_job_id)
                    job_status = job.get_status(refresh=True).value
                    if job_status in ("failed", "stopped", "canceled"):
                        status = "failed"
                        error_message = (
                            "Tác vụ đồng bộ đã thất bại hoặc quá thời gian xử lý."
                        )
                        set_sync_status_cache(
                            user_id,
                            status="failed",
                            error_message=error_message,
                            last_synced_at=last_synced_at,
                        )
                except (RedisError, OSError, TypeError) as exc:
                    logger.debug(
                        "Không thể kiểm tra trạng thái RQ job %s: %s",
                        cached_job_id,
                        exc,
                    )

            # Kiểm tra thời gian trôi qua để tránh kẹt trạng thái "running" vô hạn
            updated_at_str = cached.get("updated_at")
            if updated_at_str and status == "running":
                updated_at_dt = _parse_iso(updated_at_str)
                if updated_at_dt:
                    elapsed = (datetime.now(UTC) - updated_at_dt).total_seconds()
                    if elapsed > (settings.github_sync_timeout_seconds + 60):
                        status = "failed"
                        error_message = "Quá thời gian thực thi tác vụ đồng bộ."
                        set_sync_status_cache(
                            user_id,
                            status="failed",
                            error_message=error_message,
                            last_synced_at=last_synced_at,
                        )

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

    if hasattr(client, "__aenter__") and hasattr(client, "__aexit__"):
        async with client:
            return await _sync_repositories_for_user_impl(db, user, client)
    return await _sync_repositories_for_user_impl(db, user, client)


async def _sync_repositories_for_user_impl(
    db: Session,
    user: User,
    client: GitHubApiClient,
) -> dict[str, Any]:
    set_sync_status_cache(user.id, status="running")

    try:
        can_access_private = has_private_access(db, user.id)
        if can_access_private:
            repos_data = await client.list_repositories()
        else:
            try:
                repos_data = await client.list_repositories(visibility="public")
            except TypeError:
                repos_data = await client.list_repositories()
            repos_data = [
                r for r in repos_data if not (isinstance(r, dict) and r.get("private"))
            ]
        sync_timestamp = datetime.now(UTC)

        # 1. Deduplicate theo external_id
        unique_repos_data: list[dict[str, Any]] = []
        seen_ext_ids: set[str] = set()
        for r in repos_data:
            ext_id = str(r["id"]) if isinstance(r, dict) and "id" in r else None
            if ext_id and ext_id not in seen_ext_ids:
                seen_ext_ids.add(ext_id)
                unique_repos_data.append(r)

        external_ids = list(seen_ext_ids)

        # 2. Batch load existing Repository records từ database
        existing_repos: dict[str, Repository] = {}
        if external_ids:
            batch_size = 500
            for i in range(0, len(external_ids), batch_size):
                chunk = external_ids[i : i + batch_size]
                stmt = select(Repository).where(Repository.external_id.in_(chunk))
                for repo_obj in db.scalars(stmt):
                    existing_repos[repo_obj.external_id] = repo_obj

        # 3. Batch load existing user_repository pivot records
        existing_pivot_repo_ids: set[int] = set()
        if existing_repos:
            repo_ids = [r.id for r in existing_repos.values()]
            batch_size = 500
            for i in range(0, len(repo_ids), batch_size):
                chunk = repo_ids[i : i + batch_size]
                pivot_stmt = select(user_repository.c.repository_id).where(
                    user_repository.c.user_id == user.id,
                    user_repository.c.repository_id.in_(chunk),
                )
                existing_pivot_repo_ids.update(db.scalars(pivot_stmt).all())

        # 4. Chuẩn bị concurrent fetches cho languages và fork details
        semaphore = asyncio.Semaphore(settings.github_api_concurrency)

        async def _fetch_languages(owner: str, name: str) -> dict[str, int]:
            async with semaphore:
                try:
                    return await client.get_repository_languages(owner, name)
                except (GitHubNotFoundError, GitHubPermissionError):
                    return {}

        async def _fetch_fork_details(owner: str, name: str) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    return await client.get_repository_details(owner, name)
                except (GitHubNotFoundError, GitHubPermissionError):
                    return None

        lang_tasks: dict[int, Any] = {}
        fork_tasks: dict[int, Any] = {}
        repo_languages_map: dict[int, dict[str, int]] = {}
        repo_fork_source_map: dict[int, str | None] = {}

        for idx, repo in enumerate(unique_repos_data):
            external_id = str(repo["id"])
            name = repo.get("name") or "unknown"
            full_name = repo.get("full_name") or name
            existing = existing_repos.get(external_id)
            pushed_at = _parse_iso(repo.get("pushed_at"))
            size_kb = int(repo.get("size", 0))
            is_fork = bool(repo.get("fork", False))

            owner_info = repo.get("owner")
            owner_login = (
                owner_info.get("login") if isinstance(owner_info, dict) else None
            )
            if not owner_login and "/" in full_name:
                owner_login = full_name.split("/")[0]

            # Fork source determination
            if is_fork:
                if "parent" in repo and isinstance(repo["parent"], dict):
                    repo_fork_source_map[idx] = repo["parent"].get("full_name")
                elif existing and existing.fork_source:
                    repo_fork_source_map[idx] = existing.fork_source
                elif owner_login and name:
                    fork_tasks[idx] = _fetch_fork_details(owner_login, name)
                else:
                    repo_fork_source_map[idx] = None
            else:
                repo_fork_source_map[idx] = None

            # Language determination
            existing_pushed_at = _ensure_utc(existing.pushed_at) if existing else None
            current_pushed_at = _ensure_utc(pushed_at)

            if repo.get("size") == 0 and not repo.get("language"):
                # Repo truly empty (size == 0 and no primary language)
                repo_languages_map[idx] = {}
            elif (
                existing
                and existing.languages
                and existing_pushed_at is not None
                and current_pushed_at is not None
                and existing_pushed_at == current_pushed_at
            ):
                # Repo không thay đổi commit (pushed_at trùng khớp):
                # tái sử dụng languages đã lưu
                repo_languages_map[idx] = existing.languages
            elif owner_login and name:
                lang_tasks[idx] = _fetch_languages(owner_login, name)
            else:
                repo_languages_map[idx] = {}

        # Chạy đồng thời các tác vụ API cần thiết với Bounded Concurrency
        if lang_tasks or fork_tasks:
            lang_indices = list(lang_tasks.keys())
            fork_indices = list(fork_tasks.keys())
            all_coros = [lang_tasks[i] for i in lang_indices] + [
                fork_tasks[i] for i in fork_indices
            ]
            results = await asyncio.gather(*all_coros, return_exceptions=True)

            num_lang = len(lang_indices)
            lang_results = results[:num_lang]
            fork_results = results[num_lang:]

            for i, res in zip(lang_indices, lang_results, strict=True):
                if isinstance(res, (GitHubRateLimitError, GitHubTokenRevokedError)):
                    raise res
                if isinstance(res, Exception):
                    logger.warning("Lỗi khi tải languages cho repo %s: %s", i, res)
                    repo_languages_map[i] = {}
                else:
                    repo_languages_map[i] = res

            for i, res in zip(fork_indices, fork_results, strict=True):
                if isinstance(res, (GitHubRateLimitError, GitHubTokenRevokedError)):
                    raise res
                if (
                    isinstance(res, dict)
                    and "parent" in res
                    and isinstance(res["parent"], dict)
                ):
                    repo_fork_source_map[i] = res["parent"].get("full_name")
                else:
                    repo_fork_source_map[i] = None

        # 5. Lưu trữ dữ liệu vào database
        for idx, repo in enumerate(unique_repos_data):
            external_id = str(repo["id"])
            name = repo.get("name") or "unknown"
            full_name = repo.get("full_name") or name
            html_url = repo.get("html_url") or f"https://github.com/{full_name}"
            description = repo.get("description")
            private = bool(repo.get("private", False))
            default_branch = repo.get("default_branch") or "main"
            is_fork = bool(repo.get("fork", False))
            fork_source = repo_fork_source_map.get(idx)
            languages = repo_languages_map.get(idx) or {}

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

            existing = existing_repos.get(external_id)
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
                existing_repos[external_id] = repo_record

            # Đảm bảo liên kết trong bảng pivot user_repository
            if repo_record.id not in existing_pivot_repo_ids:
                db.execute(
                    user_repository.insert().values(
                        user_id=user.id,
                        repository_id=repo_record.id,
                        added_at=sync_timestamp,
                    )
                )
                existing_pivot_repo_ids.add(repo_record.id)

        db.commit()

        set_sync_status_cache(
            user.id,
            status="completed",
            total_synced=len(unique_repos_data),
            last_synced_at=sync_timestamp.isoformat(),
        )

        return {
            "status": "completed",
            "synced_count": len(unique_repos_data),
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
