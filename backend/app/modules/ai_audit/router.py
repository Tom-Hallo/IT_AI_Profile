"""Read-only, authenticated audit history with owner-scoped keyset pagination."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.ai_audit.models import (
    AIUsageEvent,
    Consent,
    Feature,
    Phase,
    Provider,
    Source,
    Status,
    Tool,
)
from app.modules.users.models import User

router = APIRouter(prefix="/ai-audit", tags=["AI Audit"])


class Event(BaseModel):
    id: str
    operation_id: UUID
    feature: Feature
    phase: Phase
    source: Source
    provider: Provider | None
    consent: Consent
    status: Status
    tool: Tool | None
    created_at: datetime


class EventPage(BaseModel):
    items: list[Event]
    next_before: str | None = None


@router.get("")
def history(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    before: Annotated[int | None, Query(gt=0, le=2**63 - 1)] = None,
) -> EventPage:
    response.headers["Cache-Control"] = "no-store"
    query = select(AIUsageEvent).where(AIUsageEvent.user_id == user.id)
    if before is not None:
        query = query.where(AIUsageEvent.id < before)
    rows = db.scalars(query.order_by(AIUsageEvent.id.desc()).limit(limit + 1)).all()
    visible = rows[:limit]
    return EventPage(
        items=[
            Event(
                id=str(row.id),
                operation_id=row.operation_id,
                feature=row.feature,
                phase=row.phase,
                source=row.source,
                provider=row.provider,
                consent=row.consent,
                status=row.status,
                tool=row.tool,
                created_at=row.created_at,
            )
            for row in visible
        ],
        next_before=str(visible[-1].id) if len(rows) > limit else None,
    )
