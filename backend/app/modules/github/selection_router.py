from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.modules.github.selection_schemas import (
    OptionsResponse,
    Scope,
    SelectionResponse,
    SelectionUpdate,
)
from app.modules.github.selection_service import (
    options,
    read_selection,
    update_selection,
)
from app.modules.users.models import User

router = APIRouter(prefix="/github", tags=["Repository Selection"])


@router.get("/repos", response_model=OptionsResponse)
async def list_selectable_repos(
    scope: Annotated[Scope, Query()] = "public",
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
):
    return await options(db, user.id, scope)


@router.get("/selection", response_model=SelectionResponse)
def get_saved_selection(
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
):
    return read_selection(db, user.id)


@router.put("/selection", response_model=SelectionResponse)
async def save_selection(
    payload: SelectionUpdate,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
):
    # Origin allowlist prevents cross-site browser writes with session cookies.
    origin = request.headers.get("origin")
    if not origin or origin not in settings.cors_origins:
        raise HTTPException(403, "Origin không được phép.")
    return await update_selection(db, user.id, payload)
