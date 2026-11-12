"""AI provider usage audit metadata (PBI-020).

Không lưu prompt, response, API key hoặc mã nguồn riêng tư.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIUsageLog(Base):
    """Lưu metadata sử dụng AI provider."""

    __tablename__ = "ai_usage_logs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
    )

    repository_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("ita.repositories.id", ondelete="SET NULL"),
        nullable=True,
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(20), nullable=False)

    duration_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_ai_usage_logs_user_id", "user_id"),
        Index("ix_ai_usage_logs_repository_id", "repository_id"),
        Index("ix_ai_usage_logs_created_at", "created_at"),
        {"schema": "ita"},
    )
