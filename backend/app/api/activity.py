from datetime import date
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.time_range import resolve_range
from app.dependencies import get_current_user_id, get_db
from app.services.activity import analyze

router = APIRouter(prefix='/api/v1/repositories', tags=['GitHub Activity Analysis'])

@router.get(
    '/{repository_id}/activity/analysis',
    summary='Analyze repository activity by time range',
)
async def get_activity_analysis(
    repository_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Depends(get_current_user_id)],
    mode: Literal['preset', 'month', 'custom'] = Query(...),
    preset: Literal['1m', '3m', '6m', '1y'] | None = None,
    month: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str = 'UTC',
):
    start, end = resolve_range(mode, preset, month, start_date, end_date, timezone)
    return await analyze(db, repository_id, user_id, start, end)
