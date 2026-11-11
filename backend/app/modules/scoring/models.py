"""PostgreSQL models for immutable scoring snapshots."""

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RubricVersion(Base):
    __tablename__ = "rubric_versions"
    __table_args__: ClassVar = (UniqueConstraint("kind", "version"), {"schema": "ita"})
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SkillScore(Base):
    __tablename__ = "skill_scores"
    __table_args__: ClassVar = ({"schema": "ita"},)
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.users.id"), nullable=False, index=True
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.repositories.id"), nullable=False
    )
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.analysis_reports.id"), nullable=False
    )
    rubric_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.rubric_versions.id"), nullable=False
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    technology: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ScoreEvidenceLink(Base):
    __tablename__ = "score_evidence_links"
    __table_args__: ClassVar = (
        UniqueConstraint("score_id", "evidence_id"),
        {"schema": "ita"},
    )
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    score_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.skill_scores.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.analysis_evidence.id", ondelete="RESTRICT"),
        nullable=False,
    )
