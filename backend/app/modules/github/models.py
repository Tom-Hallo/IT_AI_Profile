"""SQLAlchemy models: Repository + user_repository pivot.

PBI-002 — schema ita
<<<<<<< HEAD
=======
PBI-009 — real GitHub sync metadata
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6
"""

from __future__ import annotations

from datetime import datetime
<<<<<<< HEAD
from typing import TYPE_CHECKING
=======
from typing import TYPE_CHECKING, Any
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
<<<<<<< HEAD
=======
    Integer,
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6
    String,
    Table,
    Text,
    func,
)
<<<<<<< HEAD
=======
from sqlalchemy.dialects.postgresql import JSONB
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6
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
<<<<<<< HEAD
        BigInteger,
=======
        BigInteger().with_variant(Integer, "sqlite"),
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "repository_id",
<<<<<<< HEAD
        BigInteger,
=======
        BigInteger().with_variant(Integer, "sqlite"),
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6
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
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6
)


class Repository(Base):
    __tablename__ = "repositories"
<<<<<<< HEAD
    __table_args__ = {"schema": "ita"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
=======
    __table_args__ = {
        "schema": "ita",
        "comment": "GitHub repositories linked to a user",
    }

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6
    owner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ita.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
<<<<<<< HEAD
    html_url: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    private: Mapped[bool] = mapped_column(
        Boolean, server_default=sa.text("false"), nullable=False
    )
=======
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    html_url: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    private: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("false"), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), server_default="main", nullable=False)
    is_fork: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("false"), nullable=False)
    fork_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    languages: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    primary_language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stars_count: Mapped[int] = mapped_column(
        BigInteger, server_default=sa.text("0"), nullable=False
    )
    forks_count: Mapped[int] = mapped_column(
        BigInteger, server_default=sa.text("0"), nullable=False
    )
    open_issues_count: Mapped[int] = mapped_column(
        BigInteger, server_default=sa.text("0"), nullable=False
    )
    size_kb: Mapped[int] = mapped_column(BigInteger, server_default=sa.text("0"), nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("false"), nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("false"), nullable=False)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    github_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    github_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(50), server_default="synced", nullable=False)
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6
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
<<<<<<< HEAD

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Repository id={self.id} name={self.name!r}>"
=======
    users: Mapped[list[User]] = relationship(
        "User",
        secondary=user_repository,
        backref="associated_repositories",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Repository id={self.id} name={self.name!r} full_name={self.full_name!r}>"
>>>>>>> fc36cecf8f87eefdd7e66c02c68f921457a2aea6
