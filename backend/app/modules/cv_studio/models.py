"""Immutable snapshots of an owner's CV Studio drafts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CVStudioVersion(Base):
    __tablename__ = "cv_studio_versions"
    __table_args__ = {"schema": "ita"}

    document_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    template: Mapped[str] = mapped_column(String(20))
    lines: Mapped[list[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
