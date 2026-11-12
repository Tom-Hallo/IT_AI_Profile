"""API routes cho AI Mentor chat đa nguồn (PBI-021)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.ai_mentor.schemas import MentorChatRequest, MentorChatResponse
from app.modules.ai_mentor.service import run_mentor_chat
from app.modules.users.models import User

router = APIRouter(prefix="/mentor", tags=["AI Mentor"])


@router.post("/chat", response_model=MentorChatResponse)
async def mentor_chat(
    payload: MentorChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> MentorChatResponse:
    """Chat mentor với retrieval theo nguồn GitHub/CV/JD/Roadmap đã chọn."""
    return await run_mentor_chat(db=db, user=user, payload=payload)
