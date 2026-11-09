"""Consent API; authentication is the project's existing ita_session cookie."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.modules.consent import service
from app.modules.consent.models import PrivateConsent
from app.modules.users.models import User

router = APIRouter(prefix="/repositories", tags=["Private Consent"])
DB = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Kind = Literal["repository_access", "external_ai"]


class ConsentRequest(BaseModel):
    consent_type: Kind
    provider: str = Field(default="", max_length=80)
    scope: list[str] = Field(min_length=1, max_length=100)
    policy_version: str
    accepted: Literal[True]


def csrf(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin.rstrip("/") != settings.frontend_url.rstrip("/"):
        raise HTTPException(403, "Invalid Origin")


@router.get("/{repo_id}/consents")
def list_consents(repo_id: int, db: DB, user: CurrentUser):
    service.owned_repo(db, user.id, repo_id)
    rows = db.scalars(
        select(PrivateConsent).where(
            PrivateConsent.user_id == user.id, PrivateConsent.repository_id == repo_id
        )
    ).all()
    return {
        "policy_version": service.POLICY_VERSION,
        "consents": [
            {
                "consent_type": r.consent_type,
                "provider": r.provider_key,
                "scope": r.scope,
                "granted": r.granted
                and r.revoked_at is None
                and r.policy_version == service.POLICY_VERSION,
                "granted_at": r.granted_at,
                "revoked_at": r.revoked_at,
            }
            for r in rows
        ],
    }


@router.post("/{repo_id}/consents", status_code=201)
def create_consent(
    repo_id: int, body: ConsentRequest, request: Request, db: DB, user: CurrentUser
):
    csrf(request)
    record = service.grant(
        db,
        user.id,
        repo_id,
        body.consent_type,
        body.provider,
        body.scope,
        body.policy_version,
    )
    return {
        "id": record.id,
        "granted": record.granted,
        "policy_version": record.policy_version,
    }


@router.delete("/{repo_id}/consents/{consent_type}")
def delete_consent(
    repo_id: int,
    consent_type: Kind,
    request: Request,
    db: DB,
    user: CurrentUser,
    provider: str = Query(default=""),
):
    csrf(request)
    service.revoke(db, user.id, repo_id, consent_type, provider)
    return {"status": "revoked"}
