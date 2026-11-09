"""Versioned, user-scoped consent state and append-only audit events."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PrivateConsent(Base):
    __tablename__ = "private_consents"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "repository_id",
            "consent_type",
            "provider_key",
            name="uq_private_consent_identity",
        ),
        {"schema": "ita"},
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.users.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.repositories.id", ondelete="CASCADE"), index=True
    )
    consent_type: Mapped[str] = mapped_column(String(32))
    provider_key: Mapped[str] = mapped_column(String(80), default="")
    policy_version: Mapped[str] = mapped_column(String(30))
    scope: Mapped[list] = mapped_column(JSONB)
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrivateConsentAudit(Base):
    __tablename__ = "private_consent_audits"
    __table_args__ = {"schema": "ita"}
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    repository_id: Mapped[int] = mapped_column(BigInteger)
    consent_type: Mapped[str] = mapped_column(String(32))
    provider_key: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(20))
    policy_version: Mapped[str] = mapped_column(String(30))
    scope: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
