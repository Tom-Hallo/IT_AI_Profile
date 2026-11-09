"""RQ task. No synthetic progress, no assessment writes until pipeline integration."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.analysis.models import AnalysisJob
from app.modules.analysis.service import event


class Cancelled(Exception):
    pass


def checkpoint(job_id, token, step, progress):
    from app.db.session import session_scope

    with session_scope() as db:
        job = db.scalar(
            select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
        )
        if job.execution_token != token:
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


def run_analysis(job_id: str):
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
            return
        if job.status == "cancel_requested":
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            event(db, job, "cancelled")
            return
        job.status = "running"
        job.execution_token = token
        job.heartbeat_at = datetime.now(UTC)
        event(db, job, "started")
        user_id, repo_id = job.user_id, job.repo_id
    try:
        # Real persisted repository metadata (from PBI-009), no simulated timing.
        with session_scope() as db:
            repo = db.scalar(
                select(Repository)
                .join(user_repository, Repository.id == user_repository.c.repository_id)
                .where(Repository.id == repo_id, user_repository.c.user_id == user_id)
            )
            access, _ = get_user_github_token(db, user_id)
            if repo is None or not access:
                raise PermissionError("repository access revoked")
            metadata = {
                "repo": repo.full_name,
                "languages": repo.languages or {},
                "size_kb": repo.size_kb,
            }
        checkpoint(job_uuid, token, "metadata_loaded", 25)
        # IMPORTANT: PBI-009 currently provides repository sync, not a verified
        # scoring pipeline. Fail closed instead of fabricating scores or 100%.
        raise NotImplementedError("analysis_pipeline_not_connected")
    except Cancelled:
        return
    except Exception as exc:
        with session_scope() as db:
            job = db.scalar(
                select(AnalysisJob).where(AnalysisJob.id == job_uuid).with_for_update()
            )
            if job.execution_token == token and job.status in (
                "running",
                "cancel_requested",
            ):
                job.status = "failed" if job.status == "running" else "cancelled"
                job.error_code = type(exc).__name__ if job.status == "failed" else None
                job.finished_at = datetime.now(UTC)
                event(db, job, job.status)
        raise
