"""Persistent analysis jobs, reports & evidence (PostgreSQL schema ita)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    __table_args__ = (
        Index("ix_ita_analysis_job_events_job_id", "job_id"),
        {"schema": "ita"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ita.analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"
    __table_args__ = (
        Index("ix_analysis_reports_repo_commit", "repository_id", "commit_sha"),
        {"schema": "ita"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.repositories.id"), nullable=False, index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(40), nullable=False, default="all")
    time_range: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    structure: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    languages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    frameworks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    architecture: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AnalysisEvidence(Base):
    __tablename__ = "analysis_evidence"
    __table_args__ = (
        Index("ix_analysis_evidence_repo_commit", "repository_id", "commit_sha"),
        {"schema": "ita"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    report_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.analysis_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.repositories.id"), nullable=False, index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    classification: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(50), nullable=False)
    detection_method: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="high")
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False, default="all")
    time_range: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
