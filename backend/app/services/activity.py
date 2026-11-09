from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.github import Repository, RepositoryAccess, Commit, PullRequest, Snapshot

async def analyze(db: AsyncSession, repository_id: int, user_id: int, start, end):
    # Permission check happens before any activity lookup.
    allowed = await db.scalar(select(Repository.id).where(
        Repository.id == repository_id,
        or_(Repository.owner_user_id == user_id,
            Repository.id.in_(select(RepositoryAccess.repository_id).where(
                RepositoryAccess.user_id == user_id, RepositoryAccess.can_read.is_(True))))))
    if allowed is None:
        raise HTTPException(404, 'Repository not found')
    repo = await db.get(Repository, repository_id)
    if repo.synced_at is None:
        raise HTTPException(409, 'Repository has not completed GitHub sync')
    commits = (await db.execute(select(func.count(Commit.id),
                 func.coalesce(func.sum(Commit.additions), 0),
                 func.coalesce(func.sum(Commit.deletions), 0)).where(
                 Commit.repository_id == repository_id,
                 Commit.committed_at >= start, Commit.committed_at < end))).one()
    prs = await db.scalar(select(func.count(PullRequest.id)).where(
        PullRequest.repository_id == repository_id,
        PullRequest.created_at >= start, PullRequest.created_at < end))
    # Only a snapshot exactly at start can prove the baseline for this range.
    baseline = await db.scalar(select(Snapshot.code_lines).where(
        Snapshot.repository_id == repository_id, Snapshot.captured_at == start))
    return {
        'repository_id': repository_id,
        'period': {'start_utc': start.isoformat(), 'end_exclusive_utc': end.isoformat()},
        'activity': {'commits': commits[0], 'pull_requests_created': prs,
                     'additions': commits[1], 'deletions': commits[2]},
        'base_code': {'status': 'available' if baseline is not None else 'unavailable',
                      'lines': baseline,
                      'as_of_utc': start.isoformat() if baseline is not None else None},
        'sync': {'last_synced_at': repo.synced_at.isoformat(),
                 'complete_through_end': repo.synced_at >= end}
    }
