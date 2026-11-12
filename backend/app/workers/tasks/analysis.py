"""RQ task for repository static code, framework & architecture analysis (PBI-011 &
PBI-012).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.time_range import resolve_range
from app.modules.analysis.evidence import UTC
from app.modules.analysis.inspector import (
    RepositoryContentSource,
    RepositoryInspector,
)
from app.modules.analysis.limits import AnalysisLimits
from app.modules.analysis.models import AnalysisJob
from app.modules.analysis.schemas import VerificationRequest
from app.modules.analysis.service import (
    GitHubRepositoryContentSource,
    cache_analysis_result,
    event,
    redact_private_evidence,
    save_analysis_result,
)
from app.modules.github.client import GitHubApiClient, GitHubNotFoundError

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
    """Execute background static repository analysis job with transactional state
    checkpoints.
    """
    from app.db.session import session_scope
    from app.modules.auth.service import get_user_github_token
    from app.modules.github.models import Repository, user_repository

    job_uuid = uuid.UUID(job_id)
    cancelled_before_start = False
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
            cancelled_before_start = True
        else:
            job.status = "running"
            job.execution_token = token
            job.heartbeat_at = datetime.now(UTC)
            event(db, job, "started")
        user_id, repo_id = job.user_id, job.repo_id
        scope = job.scope
        request_options = job.request_options or {}

    try:
        if cancelled_before_start:
            return None
        verification_request = VerificationRequest(
            scope=scope if scope in ("public", "private") else "all",
            **request_options,
        )
        end_utc = None
        time_range = None
        if verification_request.mode:
            start_utc, end_utc = resolve_range(
                mode=verification_request.mode,
                preset=verification_request.preset,
                month=verification_request.month,
                year=verification_request.year,
                start_date=verification_request.start_date,
                end_date=verification_request.end_date,
                timezone_name=verification_request.timezone,
            )
            time_range = {
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
                "timezone": verification_request.timezone,
            }

        # 1. Tải và kiểm tra tính hợp lệ của repository & quyền truy cập GitHub token
        # (PBI-009/PBI-011)
        with session_scope() as db:
            repo = db.scalar(
                select(Repository)
                .join(user_repository, Repository.id == user_repository.c.repository_id)
                .where(Repository.id == repo_id, user_repository.c.user_id == user_id)
            )
            access_token, token_scope = get_user_github_token(db, user_id)
            if repo is None or not access_token:
                raise PermissionError("Repository access revoked or token missing")

            if (scope == "public" and repo.private) or (
                scope == "private" and not repo.private
            ):
                raise PermissionError("Repository visibility does not match job scope")

            # Kiểm tra quyền và sự đồng thuận đối với private repository
            if repo.private:
                from app.modules.auth.service import (
                    has_private_access,
                    has_repo_scope,
                )

                if not has_repo_scope(token_scope):
                    raise PermissionError(
                        "Private repository analysis requires "
                        "'repo' OAuth scope consent"
                    )
                if not has_private_access(db, user_id):
                    raise PermissionError("Private repository access is not authorized")
                from app.modules.consent.guards import (
                    require_private_access_consent,
                )

                try:
                    require_private_access_consent(db, user_id, repo_id)
                except Exception as ce:
                    detail = getattr(ce, "detail", str(ce))
                    raise PermissionError(
                        f"Private repository consent check failed: {detail}"
                    ) from ce

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
                    owner=owner,
                    repo=r_name,
                    branch_or_ref=verification_request.branch or default_branch,
                    until=end_utc,
                )
                if not latest_sha:
                    raise GitHubNotFoundError(
                        "Không tìm thấy commit trên nhánh trong khoảng đã chọn."
                    )
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
                time_range=time_range,
            )
            return await inspector.inspect(
                source=content_source,
                github_languages=repo_languages,
                on_progress=_on_progress,
            )

        checkpoint(job_uuid, token, "inspecting_repository_content", 30)

        # 3. Chạy phân tích tĩnh mã nguồn, framework & kiến trúc (PBI-012)
        analysis_result = asyncio.run(_execute_inspection())

        checkpoint(job_uuid, token, "verifying_fork_and_authorship", 75)

        # 4. Thu thập verification, chưa ghi database.
        verification_result = None

        if custom_source is None and access_token:
            try:
                from app.modules.analysis.verification_service import (
                    verify_repository_contributions,
                )
                from app.modules.users.models import User

                with session_scope() as verif_db:
                    user_record = verif_db.scalar(
                        select(User).where(User.id == user_id)
                    )

                    if user_record is None:
                        raise PermissionError("User no longer exists")

                    verification_result = asyncio.run(
                        verify_repository_contributions(
                            db=verif_db,
                            repository_id=repo_id,
                            user=user_record,
                            request=verification_request,
                            job_id=str(job_uuid),
                            persist=False,
                        )
                    )

            except Exception as ve:
                logger.warning(
                    "Verification collection failed for job %s: %s",
                    job_uuid,
                    ve,
                )

        checkpoint(job_uuid, token, "finalizing_evidence", 85)

        # 5. Lưu analysis, verification và job state trong một transaction.
        with session_scope() as db:
            job = db.scalar(
                select(AnalysisJob).where(AnalysisJob.id == job_uuid).with_for_update()
            )

            if job is None or job.execution_token != token:
                raise Cancelled()

            if job.status == "cancel_requested":
                job.status = "cancelled"
                job.finished_at = datetime.now(UTC)
                event(db, job, "cancelled")
                return None

            if job.status != "running":
                raise Cancelled()

            # Khóa repository để đồng bộ với thao tác thu hồi consent.
            repo = db.scalar(
                select(Repository)
                .join(
                    user_repository,
                    Repository.id == user_repository.c.repository_id,
                )
                .where(
                    Repository.id == repo_id,
                    user_repository.c.user_id == user_id,
                )
                .with_for_update(of=Repository)
            )

            if repo is None:
                raise PermissionError("Repository access was revoked")

            # Kiểm tra lại token tại thời điểm lưu.
            current_token, current_scope = get_user_github_token(db, user_id)

            if not current_token:
                raise PermissionError("GitHub access was revoked")

            if repo.private:
                from app.modules.auth.service import (
                    has_private_access,
                    has_repo_scope,
                )
                from app.modules.consent.guards import (
                    require_private_access_consent,
                )

                if not has_repo_scope(current_scope):
                    raise PermissionError("Private repository OAuth scope revoked")

                if not has_private_access(db, user_id):
                    raise PermissionError("Private repository access was revoked")

                require_private_access_consent(
                    db,
                    user_id,
                    repo_id,
                )

            if repo.private:
                redact_private_evidence(analysis_result)

            # Không commit ở đây.
            report = save_analysis_result(
                db,
                analysis_result,
                commit=False,
            )

            if report is None:
                raise RuntimeError("Analysis report was not saved")

            # Verification chỉ được ghi sau khi quyền đã được kiểm tra.
            if verification_result is not None:
                from app.modules.analysis.verification_service import (
                    persist_verification_result,
                )

                verification_result.report_id = report.id

                persist_verification_result(
                    db,
                    verification_result,
                    commit=False,
                )

            job.report_id = report.id
            job.status = "succeeded"
            job.progress = 100
            job.step = "completed"
            job.finished_at = datetime.now(UTC)

            event(db, job, "succeeded")

        cache_analysis_result(analysis_result)
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
    finally:
        try:
            from app.modules.consent.cleanup import purge_job_directory

            purge_job_directory(job_uuid)
            from app.modules.consent.cleanup_service import finish_cleanup

            with session_scope() as db:
                finish_cleanup(db, job_uuid)
        except Exception as exc:
            logger.error(
                "Lỗi dọn dẹp thư mục tạm của job %s: %s",
                job_uuid,
                type(exc).__name__,
            )
            try:
                from app.modules.consent.cleanup_service import request_cleanup

                with session_scope() as db:
                    failed_job = db.scalar(
                        select(AnalysisJob).where(AnalysisJob.id == job_uuid)
                    )
                    if failed_job:
                        request_cleanup(db, failed_job, reason="cleanup_error")
            except Exception as outbox_exc:
                logger.error(
                    "Không thể ghi outbox cleanup cho job %s: %s",
                    job_uuid,
                    type(outbox_exc).__name__,
                )
