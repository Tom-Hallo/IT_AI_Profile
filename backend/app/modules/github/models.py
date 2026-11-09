"""SQLAlchemy models: Repository + user_repository pivot.

PBI-002 — schema ita
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.users.models import User


# Many-to-many association table (pivot)
user_repository = Table(
    "user_repository",
    Base.metadata,
    sa.Column(
        "user_id",
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "repository_id",
        BigInteger,
        ForeignKey("ita.repositories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "added_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
<<<<<<< HEAD
    schema="ita",
=======
    sa.Index("ix_user_repository_user_id", "user_id"),
    schema="ita",
    comment="Pivot table: users <-> repositories (many-to-many)",
>>>>>>> d35de7782a07584638b77040b87473fd8e91f925
)


class Repository(Base):
    __tablename__ = "repositories"
<<<<<<< HEAD
    __table_args__ = {"schema": "ita"}
=======
    __table_args__ = {
        "schema": "ita",
        "comment": "GitHub repositories linked to a user",
    }
>>>>>>> d35de7782a07584638b77040b87473fd8e91f925

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    html_url: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
<<<<<<< HEAD
    private: Mapped[bool] = mapped_column(
        Boolean, server_default=sa.text("false"), nullable=False
    )
=======
    private: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("false"), nullable=False)
>>>>>>> d35de7782a07584638b77040b87473fd8e91f925
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    owner: Mapped[User] = relationship(
        "User",
        back_populates="repositories",
        foreign_keys=[owner_id],
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Repository id={self.id} name={self.name!r}>"
