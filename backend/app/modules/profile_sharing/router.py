"""PBI-037 owner-only management and anonymous read endpoints."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.profile_sharing.models import ProfileShareLink
from app.modules.profile_sharing.service import (
    ALLOWED_FIELDS,
    new_token,
    public_payload,
    token_digest,
)
from app.modules.users.models import User

router = APIRouter(tags=["Profile Sharing"])
Db = Annotated[Session, Depends(get_session)]
Owner = Annotated[User, Depends(get_current_user)]


class ShareSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_fields: set[Literal["full_name", "public_repositories"]] = Field(
        default_factory=set
    )


def owner_link(db: Session, user_id: int, link_id: int) -> ProfileShareLink:
    link = db.scalar(
        select(ProfileShareLink).where(
            ProfileShareLink.id == link_id, ProfileShareLink.user_id == user_id
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    return link


@router.post("/profile/shares/preview")
def preview(body: ShareSettings, db: Db, user: Owner) -> dict:
    return public_payload(db, user, body.allowed_fields & ALLOWED_FIELDS)


@router.post("/profile/shares", status_code=201)
def create_share(body: ShareSettings, db: Db, user: Owner) -> dict:
    token = new_token()
    link = ProfileShareLink(
        user_id=user.id,
        token_hash=token_digest(token),
        allowed_fields=sorted(body.allowed_fields),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    # Raw capability is returned exactly once; never stored in DB or logged.
    return {"id": link.id, "token": token, "allowed_fields": link.allowed_fields}


@router.put("/profile/shares/{link_id}")
def update_share(link_id: int, body: ShareSettings, db: Db, user: Owner) -> dict:
    link = owner_link(db, user.id, link_id)
    if not link.is_active:
        raise HTTPException(status_code=404, detail="Share link not found")
    link.allowed_fields = sorted(body.allowed_fields)
    db.commit()
    return {"id": link.id, "allowed_fields": link.allowed_fields}


@router.delete("/profile/shares/{link_id}", status_code=204)
def revoke_share(link_id: int, db: Db, user: Owner) -> Response:
    link = owner_link(db, user.id, link_id)
    link.is_active = False
    link.revoked_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)


@router.get("/public/profiles/{token}")
def get_public_profile(
    token: Annotated[str, Path(min_length=40, max_length=128)], db: Db
) -> dict:
    link = db.scalar(
        select(ProfileShareLink).where(
            ProfileShareLink.token_hash == token_digest(token),
            ProfileShareLink.is_active.is_(True),
            ProfileShareLink.revoked_at.is_(None),
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    user = db.get(User, link.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    return public_payload(db, user, set(link.allowed_fields) & ALLOWED_FIELDS)
