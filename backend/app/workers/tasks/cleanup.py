"""PBI-008 cleanup worker: idempotent and fail-closed."""

from uuid import UUID

from sqlalchemy import select

from app.db.session import session_scope
from app.modules.analysis.models import TERMINAL, AnalysisJob
from app.modules.consent.cleanup import purge_job_directory
from app.modules.consent.cleanup_models import CleanupRequest
from app.modules.consent.cleanup_service import finish_cleanup


def cleanup_analysis_job(job_id: str) -> bool:
    uid = UUID(job_id)
    cleanup_error = None
    with session_scope() as db:
        row = db.scalar(
            select(CleanupRequest).where(CleanupRequest.job_id == uid).with_for_update()
        )
        if row is None or row.status == "completed":
            return False
        job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == uid))
        if job is not None and job.status not in TERMINAL:
            return False
        row.attempts += 1
        try:
            purge_job_directory(uid)
        except (OSError, RuntimeError, ValueError) as exc:
            row.status = "failed"
            cleanup_error = exc
        else:
            finish_cleanup(db, uid)
    if cleanup_error is not None:
        raise cleanup_error
    return True
