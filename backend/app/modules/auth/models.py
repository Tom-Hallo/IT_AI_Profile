"""SQLAlchemy model: OAuth account linked to an application user."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.users.models import User


class OAuthAccount(Base):
    __tablename__ = "user_oauth_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_user_oauth_accounts_provider_provider_user_id",
        ),
        {"schema": "ita", "comment": "External OAuth identities linked to users"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    scope: Mapped[str | None] = mapped_column(String(255), nullable=True)

    token_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(
        "User",
        back_populates="oauth_accounts",
    )

    def __repr__(self) -> str:
        return (
            f"<OAuthAccount provider={self.provider!r} provider_user_id={self.provider_user_id!r}>"
        )
