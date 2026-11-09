import logging
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_range import resolve_range
from app.dependencies import get_current_user_id, get_db
from app.services.activity import analyze

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/repositories",
    tags=["GitHub Activity Analysis"],
)


@router.get(
    "/{repository_id}/activity/analysis",
    summary="Analyze repository activity by time range",
    responses={
        401: {"description": "Authentication required (handled by auth dependency)"},
        404: {"description": "Repository not found or access denied"},
        409: {"description": "Repository has not completed GitHub sync"},
        422: {"description": "Invalid time range or query parameters"},
        500: {"description": "Internal server error"},
    },
)
async def get_activity_analysis(
    repository_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Depends(get_current_user_id)],
    mode: Literal["preset", "month", "custom"] = Query(...),
    preset: Literal["1m", "3m", "6m", "1y"] | None = None,
    month: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str = "UTC",
):
    try:
        start, end = resolve_range(mode, preset, month, start_date, end_date, timezone)
        return await analyze(db, repository_id, user_id, start, end)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unexpected GitHub activity analysis error: repository_id=%s user_id=%s",
            repository_id,
            user_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        ) from None
