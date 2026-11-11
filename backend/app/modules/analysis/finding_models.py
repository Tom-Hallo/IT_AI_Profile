"""Versioned findings with evidence linked within the same analysis report."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisFinding(Base):
    __tablename__ = "analysis_findings"
    __table_args__ = (
        UniqueConstraint("report_id", "finding_key", name="uq_finding_report_key"),
        UniqueConstraint("id", "report_id", name="uq_finding_id_report"),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="finding_confidence_range",
        ),
        CheckConstraint(
            "status IN ('draft', 'published')", name="finding_status_valid"
        ),
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
    finding_key: Mapped[str] = mapped_column(String(255), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    classification: Mapped[str] = mapped_column(String(100), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    analyzer_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="pbi012-legacy"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FindingEvidenceLink(Base):
    __tablename__ = "finding_evidence_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["finding_id", "report_id"],
            ["ita.analysis_findings.id", "ita.analysis_findings.report_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "report_id"],
            ["ita.analysis_evidence.id", "ita.analysis_evidence.report_id"],
            ondelete="CASCADE",
        ),
        {"schema": "ita"},
    )
    finding_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    evidence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    report_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
