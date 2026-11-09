"""Transactional state operations; Redis is never the source of truth."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.analysis.models import ACTIVE, AnalysisJob, AnalysisJobEvent
from app.modules.auth.service import get_user_github_token
from app.modules.github.models import user_repository


def now():
    return datetime.now(UTC)


def require_access(db, user_id, repo_id):
    owned = db.scalar(
        select(user_repository.c.repository_id).where(
            user_repository.c.user_id == user_id,
            user_repository.c.repository_id == repo_id,
        )
    )
    if owned is None:
        raise HTTPException(404, "Repository not found")
    token, _ = get_user_github_token(db, user_id)
    if not token:
        raise HTTPException(403, "GitHub access not connected")


def event(db, job, code):
    db.add(
        AnalysisJobEvent(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            step=job.step,
            code=code,
        )
    )


def owned_job(db, user_id, job_id, lock=False):
    stmt = select(AnalysisJob).where(
        AnalysisJob.id == job_id, AnalysisJob.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update()
    job = db.scalar(stmt)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


def active_job(db, user_id, repo_id, scope):
    return db.scalar(
        select(AnalysisJob).where(
            AnalysisJob.user_id == user_id,
            AnalysisJob.repo_id == repo_id,
            AnalysisJob.scope == scope,
            AnalysisJob.status.in_(ACTIVE),
        )
    )


def create(db, user_id, repo_id, scope, retry_of=None):
    require_access(db, user_id, repo_id)
    existing = active_job(db, user_id, repo_id, scope)
    if existing:
        return existing, False
    job = AnalysisJob(user_id=user_id, repo_id=repo_id, scope=scope, retry_of=retry_of)
    db.add(job)
    event(db, job, "created")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = active_job(db, user_id, repo_id, scope)
        if existing:
            return existing, False
        raise
    db.refresh(job)
    return job, True


def cancel(db, user_id, job_id):
    job = owned_job(db, user_id, job_id, lock=True)
    if job.status not in ACTIVE:
        raise HTTPException(409, "Job is already terminal")
    if job.status != "cancel_requested":
        job.status = "cancel_requested"
        event(db, job, "cancel_requested")
        db.commit()
    return job


def retry(db, user_id, job_id):
    old = owned_job(db, user_id, job_id, lock=True)
    if old.status not in ("failed", "cancelled"):
        raise HTTPException(409, "Only failed/cancelled jobs can be retried")
    require_access(db, user_id, old.repo_id)
    repo_id, scope, old_id = old.repo_id, old.scope, old.id
    db.rollback()  # release lock before create()
    return create(db, user_id, repo_id, scope, retry_of=old_id)


def serialize(job):
    return {
        "id": str(job.id),
        "repo_id": job.repo_id,
        "scope": job.scope,
        "status": job.status,
        "progress": job.progress,
        "step": job.step,
        "error_code": job.error_code,
        "retry_of": str(job.retry_of) if job.retry_of else None,
    }


def fail_dispatch(db, job_id):
    """Persist queue failure without exposing Redis connection details."""
    job = db.scalar(
        select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
    )
    if job is not None and job.status == "queued":
        job.status = "failed"
        job.error_code = "QUEUE_UNAVAILABLE"
        job.finished_at = now()
        event(db, job, "dispatch_failed")
        db.commit()
