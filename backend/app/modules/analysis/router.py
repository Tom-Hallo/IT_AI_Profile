"""Authenticated, owner-scoped job API. Cookie session + same-origin CSRF Origin check."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.users.models import User
from app.modules.analysis import service
from app.modules.analysis.models import AnalysisJobEvent
from app.core.config import settings
from app.workers.enqueue import enqueue_task

router = APIRouter(prefix='/analysis/jobs', tags=['Analysis Jobs'])

class CreateRequest(BaseModel):
    repo_id: int = Field(gt=0)
    scope: str = Field(pattern='^(full|activity|skills)$')

def csrf(request: Request):
    origin = request.headers.get('origin')
    if not origin or origin.rstrip('/') != settings.frontend_url.rstrip('/'):
        raise HTTPException(403, 'Invalid Origin')

def dispatch(job):
    # Fixed RQ ID needed for production outbox/reconciliation. See README.
    try:
        enqueue_task('app.workers.tasks.analysis.run_analysis', str(job.id))
    except Exception:
        # Job remains queued in PostgreSQL; reconciliation must redispatch.
        pass

@router.post('', status_code=202)
def create_job(body: CreateRequest, request: Request, db: Session = Depends(get_session), user: User = Depends(get_current_user)):
    csrf(request)
    job, created = service.create(db, user.id, body.repo_id, body.scope)
    if created:
        dispatch(job)
    return service.serialize(job)

@router.get('/{job_id}')
def get_job(job_id: uuid.UUID, db: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return service.serialize(service.owned_job(db, user.id, job_id))

@router.get('/{job_id}/events')
def get_events(job_id: uuid.UUID, db: Session = Depends(get_session), user: User = Depends(get_current_user)):
    service.owned_job(db, user.id, job_id)
    rows = db.scalars(select(AnalysisJobEvent).where(AnalysisJobEvent.job_id == job_id).order_by(AnalysisJobEvent.id).limit(500)).all()
    return [{'status': e.status, 'progress': e.progress, 'step': e.step, 'code': e.code, 'created_at': e.created_at} for e in rows]

@router.post('/{job_id}/cancel', status_code=202)
def cancel_job(job_id: uuid.UUID, request: Request, db: Session = Depends(get_session), user: User = Depends(get_current_user)):
    csrf(request)
    return service.serialize(service.cancel(db, user.id, job_id))

@router.post('/{job_id}/retry', status_code=202)
def retry_job(job_id: uuid.UUID, request: Request, db: Session = Depends(get_session), user: User = Depends(get_current_user)):
    csrf(request)
    job, created = service.retry(db, user.id, job_id)
    if created:
        dispatch(job)
    return service.serialize(job)
