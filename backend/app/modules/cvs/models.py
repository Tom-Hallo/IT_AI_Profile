"""SQLAlchemy model: CV.

PBI-002 — schema ita
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.users.models import User


class CV(Base):
    __tablename__ = "cvs"
<<<<<<< HEAD
=======
<<<<<<< HEAD
    __table_args__ = {"schema": "ita"}
=======
>>>>>>> 7782749 (T065DDA: fix trang demo)
    __table_args__ = {
        "schema": "ita",
        "comment": "Versioned CV data stored as JSONB",
    }
<<<<<<< HEAD
=======
>>>>>>> d35de7782a07584638b77040b87473fd8e91f925
>>>>>>> 7782749 (T065DDA: fix trang demo)

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
