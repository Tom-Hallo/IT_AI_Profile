"""Persistent analysis jobs (PostgreSQL schema ita)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ACTIVE = ("queued", "running", "cancel_requested")
TERMINAL = ("succeeded", "failed", "cancelled")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint(
            "progress >= 0 AND progress <= 100", name="analysis_progress_range"
        ),
        Index(
            "uq_analysis_active_resource",
            "user_id",
            "repo_id",
            "scope",
            unique=True,
            postgresql_where=text("status IN ('queued','running','cancel_requested')"),
        ),
        {"schema": "ita"},
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.users.id"), nullable=False
    )
    repo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.repositories.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step: Mapped[str] = mapped_column(String(80), nullable=False, default="queued")
    error_code: Mapped[str | None] = mapped_column(String(80))
    retry_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ita.analysis_jobs.id")
    )
    execution_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisJobEvent(Base):
    __tablename__ = "analysis_job_events"
    __table_args__ = {"schema": "ita"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ita.analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
