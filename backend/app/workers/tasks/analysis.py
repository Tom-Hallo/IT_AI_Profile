"""RQ task for repository static code, framework & architecture analysis (PBI-011 & PBI-012)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.modules.analysis.evidence import UTC
from app.modules.analysis.inspector import (
    RepositoryContentSource,
    RepositoryInspector,
)
from app.modules.analysis.limits import AnalysisLimits
from app.modules.analysis.models import AnalysisJob
from app.modules.analysis.service import (
    GitHubRepositoryContentSource,
    event,
    save_analysis_result,
)
from app.modules.github.client import GitHubApiClient

logger = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


def checkpoint(job_id: uuid.UUID, token: uuid.UUID, step: str, progress: int) -> None:
    from app.db.session import session_scope

    with session_scope() as db:
        job = db.scalar(
            select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
        )
        if job is None or job.execution_token != token:
            raise Cancelled()
        if job.status == "cancel_requested":
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            event(db, job, "cancelled")
            stop = True
        else:
            stop = job.status != "running"
            if not stop:
                job.progress = max(job.progress, min(95, progress))
                job.step = step
                job.heartbeat_at = datetime.now(UTC)
                event(db, job, "progress")
    if stop:
        raise Cancelled()


def run_analysis(
    job_id: str,
    custom_source: RepositoryContentSource | None = None,
    custom_limits: AnalysisLimits | None = None,
    custom_commit_sha: str | None = None,
) -> dict[str, Any] | None:
    """Execute background static repository analysis job with transactional state checkpoints."""
    from app.db.session import session_scope
    from app.modules.auth.service import get_user_github_token
    from app.modules.github.models import Repository, user_repository

    job_uuid = uuid.UUID(job_id)
    token = uuid.uuid4()
    with session_scope() as db:
        job = db.scalar(
            select(AnalysisJob).where(AnalysisJob.id == job_uuid).with_for_update()
        )
        if job is None or job.status not in ("queued", "cancel_requested"):
            return None
        if job.status == "cancel_requested":
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            event(db, job, "cancelled")
            return None
        job.status = "running"
        job.execution_token = token
        job.heartbeat_at = datetime.now(UTC)
        event(db, job, "started")
        user_id, repo_id = job.user_id, job.repo_id
        scope = job.scope

    try:
        # 1. Tải và kiểm tra tính hợp lệ của repository & quyền truy cập GitHub token (PBI-009/PBI-011)
        with session_scope() as db:
            repo = db.scalar(
                select(Repository)
                .join(user_repository, Repository.id == user_repository.c.repository_id)
                .where(Repository.id == repo_id, user_repository.c.user_id == user_id)
            )
            access_token, token_scope = get_user_github_token(db, user_id)
            if repo is None or not access_token:
                raise PermissionError("Repository access revoked or token missing")

            # Kiểm tra quyền và sự đồng thuận đối với private repository
            if repo.private and (not token_scope or "repo" not in token_scope):
                raise PermissionError(
                    "Private repository analysis requires 'repo' OAuth scope consent"
                )

            repo_name = repo.name
            full_name = repo.full_name or repo.name
            default_branch = repo.default_branch or "main"
            repo_languages = dict(repo.languages) if repo.languages else {}

        checkpoint(job_uuid, token, "metadata_loaded", 25)

        # 2. Chuẩn bị nguồn nội dung repository (GitHub API hoặc custom test source)
        owner = full_name.split("/")[0] if "/" in full_name else repo_name
        r_name = full_name.split("/")[1] if "/" in full_name else repo_name

        def _on_progress(step: str, pct: int) -> None:
            checkpoint(job_uuid, token, step, pct)

        async def _execute_inspection() -> dict[str, Any]:
            content_source = custom_source
            commit_sha = custom_commit_sha or "0000000000000000000000000000000000000000"

            if content_source is None:
                client = GitHubApiClient(access_token=access_token)
                latest_sha = await client.get_latest_commit_sha(
                    owner=owner, repo=r_name, branch=default_branch
                )
                if latest_sha:
                    commit_sha = latest_sha
                content_source = GitHubRepositoryContentSource(
                    client=client,
                    owner=owner,
                    repo=r_name,
                    commit_sha=commit_sha,
                )

            limits = custom_limits or AnalysisLimits()
            inspector = RepositoryInspector(
                repository_id=repo_id,
                commit_sha=commit_sha,
                limits=limits,
                scope=scope,
            )
            return await inspector.inspect(
                source=content_source,
                github_languages=repo_languages,
                on_progress=_on_progress,
            )

        checkpoint(job_uuid, token, "inspecting_repository_content", 30)

        # 3. Chạy phân tích tĩnh mã nguồn, framework & kiến trúc (PBI-012)
        analysis_result = asyncio.run(_execute_inspection())

        checkpoint(job_uuid, token, "finalizing_evidence", 85)

        # 4. Bảo toàn kết quả và bằng chứng xác thực trong DB & cache
        with session_scope() as db:
            save_analysis_result(db, analysis_result)

        # 5. Cập nhật trạng thái thành công hoàn tất (succeeded)
        with session_scope() as db:
            job = db.scalar(
                select(AnalysisJob).where(AnalysisJob.id == job_uuid).with_for_update()
            )
            if job and job.execution_token == token and job.status == "running":
                job.status = "succeeded"
                job.progress = 100
                job.step = "completed"
                job.finished_at = datetime.now(UTC)
                event(db, job, "succeeded")

        return analysis_result

    except Cancelled:
        return None
    except Exception as exc:
        with session_scope() as db:
            job = db.scalar(
                select(AnalysisJob).where(AnalysisJob.id == job_uuid).with_for_update()
            )
            if (
                job
                and job.execution_token == token
                and job.status
                in (
                    "running",
                    "cancel_requested",
                )
            ):
                job.status = "failed" if job.status == "running" else "cancelled"
                job.error_code = type(exc).__name__ if job.status == "failed" else None
                job.finished_at = datetime.now(UTC)
                event(db, job, job.status)
        raise
