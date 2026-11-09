"""Run periodically via scheduler or as a separate process: python -m
app.workers.tasks.cleanup_dispatcher
"""

from sqlalchemy import select

from app.db.session import session_scope
from app.modules.analysis.models import TERMINAL, AnalysisJob
from app.modules.consent.cleanup_models import CleanupRequest
from app.workers.tasks.cleanup import cleanup_analysis_job


def dispatch_once() -> int:
    with session_scope() as db:
        ids = [
            str(r.job_id)
            for r in db.scalars(
                select(CleanupRequest)
                .join(AnalysisJob, AnalysisJob.id == CleanupRequest.job_id)
                .where(
                    CleanupRequest.status.in_(("pending", "failed")),
                    AnalysisJob.status.in_(TERMINAL),
                )
                .limit(100)
            ).all()
        ]
    count = 0
    for job_id in ids:
        try:
            if cleanup_analysis_job(job_id):
                count += 1
        except (OSError, RuntimeError, ValueError):
            # Error state persisted; next scheduled pass retries.
            continue
    return count


if __name__ == "__main__":
    print(f"cleanup completed: {dispatch_once()}")
