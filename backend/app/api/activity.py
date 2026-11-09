"""PBI-010: integrated endpoint using existing session and PostgreSQL dependencies."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.time_range import resolve_range
from app.db.session import get_session
from app.modules.users.models import User
from app.services.activity import analyze

router = APIRouter(prefix="/repositories", tags=["GitHub Activity Analysis"])


@router.get(
    "/{repository_id}/activity/analysis",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "GitHub access forbidden"},
        404: {"description": "Repository missing or inaccessible"},
        409: {"description": "Sync not completed"},
        413: {"description": "Reduce the time window"},
        422: {"description": "Invalid filter"},
        429: {"description": "GitHub rate limit"},
        502: {"description": "GitHub upstream error"},
    },
)
async def get_activity_analysis(
    repository_id: int,
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    mode: Literal["preset", "month", "year", "custom"] = Query(...),
    preset: Literal["1m", "3m", "6m", "1y", "all"] | None = None,
    month: str | None = None,
    year: str | int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str = "UTC",
):
    start, end = resolve_range(
        mode=mode,
        preset=preset,
        month=month,
        year=year,
        start_date=start_date,
        end_date=end_date,
        timezone_name=timezone,
    )
    return await analyze(db, repository_id, user.id, start, end)
