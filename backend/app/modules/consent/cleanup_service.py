"""Cleanup outbox operations. No source or filesystem path in DB."""
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.consent.cleanup_models import CleanupRequest
from app.modules.analysis.models import AnalysisJob


def request_cleanup(db: Session, job: AnalysisJob, reason: str) -> None:
    row = db.scalar(select(CleanupRequest).where(CleanupRequest.job_id == job.id))
    if row is None:
        db.add(CleanupRequest(job_id=job.id, user_id=job.user_id, repository_id=job.repo_id, reason=reason, status="pending"))
    elif row.status != "completed":
        row.status = "pending"


def finish_cleanup(db: Session, job_id: UUID) -> None:
    row = db.scalar(select(CleanupRequest).where(CleanupRequest.job_id == job_id).with_for_update())
    if row is not None:
        row.status = "completed"
        row.completed_at = datetime.now(UTC)


def cleanup_status(db: Session, user_id: int, repo_id: int) -> list[dict]:
    rows = db.scalars(select(CleanupRequest).where(CleanupRequest.user_id == user_id, CleanupRequest.repository_id == repo_id).order_by(CleanupRequest.created_at.desc()).limit(50)).all()
    return [{"job_id": str(row.job_id), "status": row.status, "reason": row.reason, "completed_at": row.completed_at} for row in rows]
