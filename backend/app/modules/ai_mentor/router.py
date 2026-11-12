"""API routes cho AI Mentor chat đa nguồn (PBI-021)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.ai_mentor.schemas import (
    MentorChatRequest,
    MentorChatResponse,
    MentorSourceOptions,
)
from app.modules.ai_mentor.service import list_source_options, run_mentor_chat
from app.modules.consent.router import csrf
from app.modules.users.models import User

router = APIRouter(prefix="/mentor", tags=["AI Mentor"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_session)]


@router.get("/sources")
def mentor_sources(
    response: Response, user: CurrentUser, db: DB
) -> MentorSourceOptions:
    response.headers["Cache-Control"] = "no-store"
    return list_source_options(db, user.id)


@router.post("/chat", dependencies=[Depends(csrf)])
async def mentor_chat(
    payload: MentorChatRequest, response: Response, user: CurrentUser, db: DB
) -> MentorChatResponse:
    response.headers["Cache-Control"] = "no-store"
    return await run_mentor_chat(db=db, user=user, payload=payload)
