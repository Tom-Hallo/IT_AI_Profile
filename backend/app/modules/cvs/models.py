"""SQLAlchemy model: CV.

PBI-002 — schema ita
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.users.models import User


class CV(Base):
    __tablename__ = "cvs"
    __table_args__ = {"schema": "ita"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="cvs")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CV id={self.id} user_id={self.user_id}>"
