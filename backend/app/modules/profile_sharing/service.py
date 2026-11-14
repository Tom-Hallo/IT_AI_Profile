"""Explicitly constructed public payloads; no ORM serialization."""

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.github.models import Repository
from app.modules.users.models import User

ALLOWED_FIELDS = frozenset({"full_name", "public_repositories"})


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_payload(db: Session, user: User, fields: set[str]) -> dict:
    """Build payload from explicit safe values only; never return raw model data."""
    result: dict = {}
    if "full_name" in fields:
        result["full_name"] = user.full_name
    if "public_repositories" in fields:
        repos = db.scalars(
            select(Repository)
            .where(
                Repository.owner_id == user.id,
                Repository.private.is_(False),
            )
            .order_by(Repository.id)
        ).all()
        result["public_repositories"] = [
            {"name": r.name, "url": r.html_url, "language": r.primary_language}
            for r in repos
            if r.html_url.startswith("https://github.com/")
        ]
    return result
