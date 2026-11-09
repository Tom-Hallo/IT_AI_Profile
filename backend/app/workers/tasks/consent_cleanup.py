"""RQ cleanup task; safe to retry. Never log paths, source code or tokens."""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import session_scope
from app.modules.analysis.models import ACTIVE, AnalysisJob
from app.modules.consent.cleanup import cleanup_terminal_jobs


def run_cleanup(user_id: int, repo_id: int) -> int:
    with session_scope() as db:
        active = db.scalar(
            select(AnalysisJob.id)
            .where(
                AnalysisJob.user_id == user_id,
                AnalysisJob.repo_id == repo_id,
                AnalysisJob.status.in_(ACTIVE),
            )
            .limit(1)
        )
        if active is not None:
            # Retry later, after worker cancellation checkpoint.
            raise RuntimeError("CLEANUP_WAITING_FOR_JOBS")
        return cleanup_terminal_jobs(db, user_id, repo_id)
