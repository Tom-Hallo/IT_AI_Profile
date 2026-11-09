"""PBI-006: persistent user-owned repository analysis selections."""

from typing import ClassVar

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RepositorySelectionSetting(Base):
    __tablename__ = "repository_selection_settings"
    __table_args__: ClassVar = (
        CheckConstraint(
            "scope IN ('public', 'private', 'combined')", name="valid_scope"
        ),
        {"schema": "ita"},
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.users.id", ondelete="CASCADE"), primary_key=True
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="public")


class RepositorySelection(Base):
    __tablename__ = "repository_selections"
    __table_args__: ClassVar = {"schema": "ita"}
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ita.users.id", ondelete="CASCADE"), primary_key=True
    )
    github_repository_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
