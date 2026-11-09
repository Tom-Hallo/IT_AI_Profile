"""Authenticated, owner-scoped analysis job API."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.modules.analysis import service
from app.modules.analysis.models import AnalysisJobEvent
from app.modules.users.models import User
from app.workers.enqueue import enqueue_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis/jobs", tags=["Analysis Jobs"])


class CreateRequest(BaseModel):
    repo_id: int = Field(gt=0)
    scope: str = Field(pattern=r"^(full|activity|skills)$")


def csrf(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin.rstrip("/") != settings.frontend_url.rstrip("/"):
        raise HTTPException(status_code=403, detail="Invalid Origin")


def dispatch(job, db: Session) -> None:
    """Fail closed if Redis cannot accept the job; do not leave it queued."""
    try:
        enqueue_task("app.workers.tasks.analysis.run_analysis", str(job.id))
    except (RedisError, ConnectionError, TimeoutError) as exc:
        logger.error("Analysis enqueue failed: %s", type(exc).__name__)
        service.fail_dispatch(db, job.id)
        raise HTTPException(
            status_code=503,
            detail="Analysis queue unavailable. Please retry later.",
        ) from exc


@router.post("", status_code=202)
def create_job(
    body: CreateRequest,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    csrf(request)
    job, created = service.create(db, user.id, body.repo_id, body.scope)
    if created:
        dispatch(job, db)
    return service.serialize(job)


@router.get("/{job_id}")
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return service.serialize(service.owned_job(db, user.id, job_id))


@router.get("/{job_id}/events")
def get_events(
    job_id: uuid.UUID,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service.owned_job(db, user.id, job_id)
    rows = db.scalars(
        select(AnalysisJobEvent)
        .where(AnalysisJobEvent.job_id == job_id)
        .order_by(AnalysisJobEvent.id)
        .limit(500)
    ).all()
    return [
        {
            "status": item.status,
            "progress": item.progress,
            "step": item.step,
            "code": item.code,
            "created_at": item.created_at,
        }
        for item in rows
    ]


@router.post("/{job_id}/cancel", status_code=202)
def cancel_job(
    job_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    csrf(request)
    return service.serialize(service.cancel(db, user.id, job_id))


@router.post("/{job_id}/retry", status_code=202)
def retry_job(
    job_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    csrf(request)
    job, created = service.retry(db, user.id, job_id)
    if created:
        dispatch(job, db)
    return service.serialize(job)
