"""Database models for user-declared skills and their private evidence."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SelfReportedSkill(Base):
    __tablename__ = "self_reported_skills"
    __table_args__ = (
        CheckConstraint(
            "status = 'self-reported'",
            name="self_reported_skill_status",
        ),
        {"schema": "ita"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="self-reported",
        server_default="self-reported",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="self-reported",
        server_default="self-reported",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SelfReportedSkillEvidence(Base):
    __tablename__ = "self_reported_skill_evidence"
    __table_args__ = (
        CheckConstraint(
            "source = 'self-reported'",
            name="self_reported_evidence_source",
        ),
        CheckConstraint(
            "status = 'self-reported'",
            name="self_reported_evidence_status",
        ),
        {"schema": "ita"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    skill_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.self_reported_skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="self-reported",
        server_default="self-reported",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="self-reported",
        server_default="self-reported",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
