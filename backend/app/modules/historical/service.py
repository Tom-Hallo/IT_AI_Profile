from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters import get_analysis_adapter
from .contracts import ReanalysisRequest
from .models import HistoricalReanalysisJob, HistoricalSnapshot


def process_job(session: Session, job_id: UUID) -> None:
    """RQ entrypoint wrapper must provide a fresh session and call this function."""
    job = session.execute(select(HistoricalReanalysisJob).where(HistoricalReanalysisJob.id == job_id).with_for_update()).scalar_one()
    if job.status == "succeeded":
        return
    if job.status not in {"queued", "failed"}:
        raise ValueError("Job is not available for execution")
    job.status = "running"
    job.error_code = None
    session.commit()
    try:
        request = ReanalysisRequest.model_validate(job.request_payload)
        result = get_analysis_adapter().analyze(job.owner_id, request)
        # Atomic success: snapshot INSERT and job status update in one transaction.
        snapshot = HistoricalSnapshot(
            owner_id=job.owner_id, source_job_id=job.id, visibility=request.visibility,
            scope=request.scope, rubric_version=request.rubric_version,
            window_start=request.window_start, window_end=request.window_end,
            score=result.score, skills=result.skills, evidence_summary=result.evidence_summary,
            source_fingerprint=result.source_fingerprint,
        )
        session.add(snapshot)
        session.flush()
        job.snapshot_id = snapshot.id
        job.status = "succeeded"
        session.commit()
    except Exception:
        session.rollback()
        job = session.get(HistoricalReanalysisJob, job_id)
        job.status = "failed"
        job.error_code = "ANALYSIS_FAILED"  # never expose provider exception/token
        session.commit()
        raise
