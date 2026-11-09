"""SQLAlchemy model: Assessment.

PBI-002 — schema ita
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.users.models import User


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
<<<<<<< HEAD
        CheckConstraint("score >= 0 AND score <= 100", name="ck_assessments_score_range"),
        {"schema": "ita"},
=======
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_assessments_score_range",
        ),
        {
            "schema": "ita",
            "comment": "Skill assessment results for a user",
        },
>>>>>>> d35de7782a07584638b77040b87473fd8e91f925
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="assessments")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Assessment id={self.id} type={self.type!r} score={self.score}>"
