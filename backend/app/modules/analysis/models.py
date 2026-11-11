"""Persistent analysis jobs, reports & evidence (PostgreSQL schema ita)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    request_options: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True)
    )
    report_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ita.analysis_reports.id", ondelete="SET NULL")
    )
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
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
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
        UniqueConstraint("id", "report_id", name="uq_analysis_evidence_id_report"),
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


class RepositoryVerification(Base):
    """Xác minh fork, ownership & đóng góp thực tế của developer (PBI-013)."""

    __tablename__ = "repository_verifications"
    __table_args__ = (
        Index("ix_repo_verif_repo_user", "repository_id", "user_id"),
        {"schema": "ita"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ita.analysis_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    report_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("ita.analysis_reports.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Provenance
    provenance_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="original"
    )
    ownership_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="owner"
    )
    is_fork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_repo_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_repo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parent_metadata_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="none"
    )

    # Verification status
    verification_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown"
    )
    coverage_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="complete"
    )
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="high")

    # Metrics
    verified_commits_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    unverified_commits_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    verified_prs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unverified_prs_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    verified_additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified_deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    time_range: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    summary_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VerificationEvidence(Base):
    """Bằng chứng xác thực đóng góp commit / PR / provenance (PBI-013)."""

    __tablename__ = "verification_evidence"
    __table_args__ = (
        Index("ix_verif_ev_verif_id", "verification_id"),
        Index("ix_verif_ev_target", "repository_id", "target_identifier"),
        {"schema": "ita"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    verification_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.repository_verifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    html_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title_or_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_merge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fork_inherited: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    additions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deletions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pr_merged: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source_repo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_repo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CollaborationAnalysis(Base):
    """Phân tích Pull Request, Review, CI & xử lý lỗi (PBI-014)."""

    __tablename__ = "collaboration_analyses"
    __table_args__ = (
        Index("ix_collab_analysis_repo_user", "repository_id", "user_id"),
        {"schema": "ita"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ita.analysis_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    report_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("ita.analysis_reports.id", ondelete="SET NULL"),
        nullable=True,
    )

    # PR Metrics
    total_prs_analyzed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    merged_prs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    closed_unmerged_prs_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    open_prs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_prs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    external_prs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Review Metrics
    total_reviews_analyzed: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    approved_reviews_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    changes_requested_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    commented_reviews_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    dismissed_reviews_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    user_reviews_conducted_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    user_reviews_received_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # CI Checks Metrics
    total_checks_analyzed: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    successful_checks_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    failed_checks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_checks_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    other_checks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    problem_solving_sequences_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Coverage & Confidence
    coverage_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="complete"
    )
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="high")

    time_range: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    collaboration_observations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    problem_solving_observations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    summary_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CollaborationEvidence(Base):
    """Bằng chứng chi tiết Pull Request, Review, CI & xử lý lỗi (PBI-014)."""

    __tablename__ = "collaboration_evidence"
    __table_args__ = (
        Index("ix_collab_ev_analysis_id", "analysis_id"),
        Index("ix_collab_ev_repo_target", "repository_id", "target_identifier"),
        Index("ix_collab_ev_pr_number", "pr_number"),
        Index("ix_collab_ev_commit_sha", "commit_sha"),
        {"schema": "ita"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    analysis_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.collaboration_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    evidence_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # pull_request, review, check_run, commit_status, problem_solving_sequence
    target_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    check_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    conclusion: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actor_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_profile_owner: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    html_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title_or_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
