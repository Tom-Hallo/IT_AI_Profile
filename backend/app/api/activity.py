from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.time_range import resolve_range
from app.services.activity import analyze
from app.dependencies import get_db, get_current_user_id

router = APIRouter(prefix='/api/v1/repositories', tags=['GitHub Activity Analysis'])

@router.get('/{repository_id}/activity/analysis', summary='Analyze repository activity by time range')
async def get_activity_analysis(
    repository_id: int,
    mode: Literal['preset', 'month', 'custom'] = Query(...),
    preset: Literal['1m', '3m', '6m', '1y'] | None = None,
    month: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str = 'UTC',
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    start, end = resolve_range(mode, preset, month, start_date, end_date, timezone)
    return await analyze(db, repository_id, user_id, start, end)
