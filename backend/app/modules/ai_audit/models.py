"""Metadata-only events. Every descriptive column has a database allowlist."""

from datetime import datetime
from typing import Literal, get_args
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

Provider = Literal["openai", "ollama"]
Feature = Literal["mentor", "cv_studio", "repository_ai"]
Phase = Literal["context", "provider", "tool"]
Source = Literal[
    "github", "github_public", "github_private", "cv", "jd", "roadmap", "chat"
]
Consent = Literal[
    "selected",
    "double_granted",
    "policy_allowed",
    "denied",
    "confirmed",
    "declined",
    "not_requested",
]
Status = Literal[
    "retrieved",
    "unavailable",
    "started",
    "succeeded",
    "denied",
    "failed",
    "timeout",
    "cancelled",
    "skipped",
    "proposed",
    "confirmed",
    "declined",
    "expired",
    "queue_deferred",
]
Tool = Literal["create_cv", "create_roadmap", "reanalyze_repository"]


def choices(values, name: str):
    return Enum(
        *get_args(values),
        name=name,
        native_enum=False,
        length=24,
        create_constraint=True,
        validate_strings=True,
    )


class AIUsageEvent(Base):
    __tablename__ = "ai_usage_events"
    __table_args__ = (
        Index("ix_ai_usage_events_owner_id", "user_id", "id"),
        {"schema": "ita"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.users.id", ondelete="CASCADE")
    )
    operation_id: Mapped[UUID] = mapped_column(Uuid)
    feature: Mapped[Feature] = mapped_column(choices(Feature, "ai_event_feature"))
    phase: Mapped[Phase] = mapped_column(choices(Phase, "ai_event_phase"))
    source: Mapped[Source] = mapped_column(choices(Source, "ai_event_source"))
    provider: Mapped[Provider | None] = mapped_column(
        choices(Provider, "ai_event_provider")
    )
    consent: Mapped[Consent] = mapped_column(choices(Consent, "ai_event_consent"))
    status: Mapped[Status] = mapped_column(choices(Status, "ai_event_status"))
    tool: Mapped[Tool | None] = mapped_column(choices(Tool, "ai_event_tool"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
