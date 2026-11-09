"""SQLAlchemy model: User.

PBI-002 — schema ita
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.assessments.models import Assessment
    from app.modules.auth.models import OAuthAccount
    from app.modules.cvs.models import CV
    from app.modules.github.models import Repository
    from app.modules.roadmaps.models import Roadmap


class User(Base):
    __tablename__ = "users"

    __table_args__: ClassVar[dict[str, str]] = {
        "schema": "ita",
        "comment": "Application users",
    }

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # GitHub OAuth users do not have an internal password.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Relationships
    repositories: Mapped[list[Repository]] = relationship(
        "Repository",
        back_populates="owner",
        cascade="all, delete-orphan",
        foreign_keys="[Repository.owner_id]",
    )
    assessments: Mapped[list[Assessment]] = relationship(
        "Assessment",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    cvs: Mapped[list[CV]] = relationship(
        "CV",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    roadmaps: Mapped[list[Roadmap]] = relationship(
        "Roadmap",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r}>"
