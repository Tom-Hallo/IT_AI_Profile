"""PBI-024 isolated milestone tracking tables; schema ita."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Milestone(Base):
    __tablename__ = "roadmap_milestones"
    __table_args__ = (
        UniqueConstraint("roadmap_id", "external_key", name="uq_rm_milestone_key"),
        {"schema": "ita"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    roadmap_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.roadmaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    required_skills: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MilestoneHistory(Base):
    __tablename__ = "roadmap_milestone_history"
    __table_args__ = {"schema": "ita"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    milestone_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.roadmap_milestones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.users.id"), nullable=False
    )
    old_status: Mapped[str | None] = mapped_column(String(24))
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RoadmapSuggestion(Base):
    __tablename__ = "roadmap_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "roadmap_id",
            "snapshot_key",
            "milestone_id",
            "action",
            name="uq_rm_suggestion_idempotent",
        ),
        {"schema": "ita"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    roadmap_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.roadmaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    milestone_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.roadmap_milestones.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_key: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
