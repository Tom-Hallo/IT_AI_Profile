"""PBI-008: cleanup temporary per-job files; never delete arbitrary paths."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select

from app.modules.analysis.models import ACTIVE, AnalysisJob

# This is a dedicated disposable root, not a Git checkout or project directory.
ROOT = Path(os.environ.get("ITA_TEMP_CODE_ROOT", "/tmp/ita-private-code")).resolve()


def job_directory(job_id: uuid.UUID) -> Path:
    """Deterministic, unguessable-enough namespace; UUID validated before path use."""
    return ROOT / str(job_id)


def purge_job_directory(job_id: uuid.UUID) -> None:
    """Only purge a single UUID-named child of the dedicated temporary root."""
    path = job_directory(job_id)
    if path.is_symlink():
        path.unlink()
        return
    if not path.exists():
        return
    if not path.is_dir() or path.parent != ROOT:
        raise ValueError("Unsafe temporary path")
    shutil.rmtree(path)


def cleanup_terminal_jobs(db, user_id: int, repository_id: int) -> int:
    """Delete only terminal job folders. Running jobs must stop first."""
    jobs = db.scalars(
        select(AnalysisJob).where(
            AnalysisJob.user_id == user_id,
            AnalysisJob.repo_id == repository_id,
            AnalysisJob.status.notin_(ACTIVE),
        )
    ).all()
    for job in jobs:
        purge_job_directory(job.id)
    return len(jobs)


def cleanup_job_directory(root: Path, job_id: uuid.UUID) -> bool:
    """Remove one UUID-named disposable directory within an explicit root.

    Return True when a directory or symlink was removed, False when absent.
    Never follow a symlink at the job-directory boundary.
    """
    if not isinstance(job_id, uuid.UUID):
        raise TypeError("job_id must be a UUID")
    root = Path(root).resolve()
    path = root / str(job_id)
    if path.is_symlink():
        path.unlink()
        return True
    if not path.exists():
        return False
    if not path.is_dir():
        raise ValueError("Unsafe temporary path")
    shutil.rmtree(path)
    return True
