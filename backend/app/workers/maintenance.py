"""Recover orphaned analysis jobs and retry cleanup from PostgreSQL."""

import logging
import time
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import session_scope
from app.modules.ai_mentor.actions import expire_pending_actions
from app.modules.analysis.models import ACTIVE, AnalysisJob
from app.modules.analysis.service import event
from app.modules.consent.cleanup_service import request_cleanup
from app.workers.enqueue import enqueue_task
from app.workers.queues import JOB_TIMEOUT_SECONDS
from app.workers.tasks.cleanup_dispatcher import dispatch_once

logger = logging.getLogger(__name__)
INTERVAL = 15
EXPIRED_RQ_STATES = {"failed", "finished", "canceled", "stopped"}


def recover_analysis_jobs() -> None:
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=JOB_TIMEOUT_SECONDS + 60)
    ready = now - timedelta(seconds=INTERVAL)
    with session_scope() as db:
        jobs = db.scalars(
            select(AnalysisJob)
            .where(
                AnalysisJob.status.in_(ACTIVE),
                or_(
                    func.coalesce(AnalysisJob.heartbeat_at, AnalysisJob.created_at)
                    < stale,
                    AnalysisJob.status.in_(("queued", "cancel_requested"))
                    & AnalysisJob.execution_token.is_(None)
                    & (AnalysisJob.created_at < ready),
                ),
            )
            .order_by(AnalysisJob.created_at, AnalysisJob.id)
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            if job.execution_token is None and job.status != "running":
                try:
                    rq_job = enqueue_task(
                        "app.workers.tasks.analysis.run_analysis",
                        str(job.id),
                        job_id=f"analysis-{job.id}",
                    )
                    if rq_job.get_status(refresh=False) not in EXPIRED_RQ_STATES:
                        continue
                except (RedisError, OSError) as exc:
                    logger.warning(
                        "Không thể phục hồi job %s: %s", job.id, type(exc).__name__
                    )
                    continue
            job.status = "cancelled" if job.status == "cancel_requested" else "failed"
            job.error_code = "WORKER_INTERRUPTED" if job.status == "failed" else None
            job.step = job.status
            job.finished_at = now
            event(db, job, job.status)
            request_cleanup(db, job, reason="worker_interrupted")


def clear_expired_mentor_actions() -> None:
    with session_scope() as db:
        expire_pending_actions(db)


def main() -> None:
    configure_logging(settings.log_level)
    while True:
        for task in (
            recover_analysis_jobs,
            dispatch_once,
            clear_expired_mentor_actions,
        ):
            try:
                task()
            except Exception as exc:
                logger.warning(
                    "Maintenance %s failed: %s", task.__name__, type(exc).__name__
                )
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
