"""PBI-008 cleanup worker: idempotent and fail-closed."""
from pathlib import Path
from uuid import UUID
from sqlalchemy import select
from app.core.config import settings
from app.db.session import session_scope
from app.modules.analysis.models import AnalysisJob, TERMINAL
from app.modules.consent.cleanup import cleanup_job_directory
from app.modules.consent.cleanup_models import CleanupRequest
from app.modules.consent.cleanup_service import finish_cleanup


def cleanup_analysis_job(job_id: str) -> bool:
    uid = UUID(job_id)
    root = Path(settings.ita_analysis_tmp_root)
    with session_scope() as db:
        row = db.scalar(select(CleanupRequest).where(CleanupRequest.job_id == uid).with_for_update())
        if row is None or row.status == "completed":
            return False
        job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == uid))
        if job is not None and job.status not in TERMINAL:
            return False
        row.status = "running"
        row.attempts += 1
    try:
        cleanup_job_directory(root, uid)
    except (OSError, RuntimeError, ValueError):
        with session_scope() as db:
            row = db.scalar(select(CleanupRequest).where(CleanupRequest.job_id == uid).with_for_update())
            if row:
                row.status = "failed"
        raise
    with session_scope() as db:
        finish_cleanup(db, uid)
    return True
