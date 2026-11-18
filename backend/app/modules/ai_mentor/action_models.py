"""Durable action state and metadata-only audit events."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MentorAction(Base):
    __tablename__ = "mentor_actions"
    __table_args__ = (
        Index("ix_mentor_actions_status_expires_at", "status", "expires_at"),
        {"schema": "ita"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.users.id", ondelete="CASCADE"), index=True
    )
    tool: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    result_id: Mapped[str | None] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MentorActionEvent(Base):
    __tablename__ = "mentor_action_events"
    __table_args__ = {"schema": "ita"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("ita.mentor_actions.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
