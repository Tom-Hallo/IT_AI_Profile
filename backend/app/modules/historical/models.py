from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base  # ADAPTER: adjust import to actual project Base


class HistoricalSnapshot(Base):
    __tablename__ = "historical_snapshots"
    __table_args__: ClassVar = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_snapshot_score"),
        Index("ix_snapshot_owner_created", "owner_id", "created_at"),
        {"schema": "ita"},
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("ita.users.id"), nullable=False)
    source_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    skills: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class HistoricalReanalysisJob(Base):
    __tablename__ = "historical_reanalysis_jobs"
    __table_args__: ClassVar = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_reanalysis_owner_key"),
        {"schema": "ita"},
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("ita.users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
