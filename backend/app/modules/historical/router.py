from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

# ADAPTER: replace with actual PBI auth + DB dependencies, preserving user identity.
from app.api.deps import get_current_user, get_db  # project-specific integration seam

from .compare import SnapshotView, compare_snapshots
from .contracts import ReanalysisRequest
from .models import HistoricalReanalysisJob, HistoricalSnapshot

router = APIRouter(prefix="/historical", tags=["Historical Snapshots"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[object, Depends(get_current_user)]
IdempotencyKey = Annotated[str, Header(min_length=8, max_length=128)]


def require_owner(
    session: Session, snapshot_id: UUID, owner_id: int
) -> HistoricalSnapshot:
    snapshot = session.scalar(
        select(HistoricalSnapshot).where(
            HistoricalSnapshot.id == snapshot_id,
            HistoricalSnapshot.owner_id == owner_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


@router.post("/reanalysis", status_code=202)
def reanalyze(
    payload: ReanalysisRequest,
    idempotency_key: IdempotencyKey,
    session: SessionDep,
    user: CurrentUserDep,
):
    if payload.visibility == "private":
        # ADAPTER: verify PBI-007 consent and allowed repository selection here.
        raise HTTPException(
            status_code=503, detail="Private consent adapter not connected"
        )
    existing = session.scalar(
        select(HistoricalReanalysisJob).where(
            HistoricalReanalysisJob.owner_id == user.id,
            HistoricalReanalysisJob.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return {"job_id": existing.id, "status": existing.status}
    job = HistoricalReanalysisJob(
        owner_id=user.id,
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        status="queued",
    )
    session.add(job)
    session.commit()
    # ADAPTER PBI-011: enqueue job.id with existing RQ worker AFTER commit.
    # Production must fail closed until enqueue is wired; do not claim processing.
    return {
        "job_id": job.id,
        "status": "queued",
        "integration_required": "PBI-011 enqueue",
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID, session: SessionDep, user: CurrentUserDep):
    job = session.scalar(
        select(HistoricalReanalysisJob).where(
            HistoricalReanalysisJob.id == job_id,
            HistoricalReanalysisJob.owner_id == user.id,
        )
    )
    if job is None:
        raise HTTPException(404, "Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "snapshot_id": job.snapshot_id,
        "error_code": job.error_code,
    }


@router.get("/snapshots")
def list_snapshots(session: SessionDep, user: CurrentUserDep):
    rows = session.scalars(
        select(HistoricalSnapshot)
        .where(HistoricalSnapshot.owner_id == user.id)
        .order_by(HistoricalSnapshot.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "id": x.id,
            "score": x.score,
            "scope": x.scope,
            "rubric_version": x.rubric_version,
            "window_start": x.window_start,
            "window_end": x.window_end,
            "created_at": x.created_at,
        }
        for x in rows
    ]


@router.get("/compare")
def compare(
    old_id: UUID,
    new_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
):
    a = require_owner(session, old_id, user.id)
    b = require_owner(session, new_id, user.id)

    def view(s):
        return SnapshotView(
            s.scope,
            s.rubric_version,
            s.window_start.isoformat(),
            s.window_end.isoformat(),
            s.score,
            s.skills,
        )

    return compare_snapshots(view(a), view(b))
