from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "github_repositories"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RepositoryAccess(Base):
    __tablename__ = "repository_access"
    __table_args__ = (UniqueConstraint("repository_id", "user_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("github_repositories.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    can_read: Mapped[bool] = mapped_column(Boolean, default=True)


class Commit(Base):
    __tablename__ = "github_commits"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("github_repositories.id"), index=True)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)


class PullRequest(Base):
    __tablename__ = "github_pull_requests"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("github_repositories.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Snapshot(Base):
    __tablename__ = "github_repository_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("github_repositories.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    code_lines: Mapped[int] = mapped_column(Integer)
    # snapshot must represent tree at this exact point, not a later repository state
