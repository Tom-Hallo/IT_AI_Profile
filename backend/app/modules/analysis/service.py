"""Service layer for repository analysis, authorization, evidence preservation, and background job state (PBI-011 & PBI-012)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.time_range import resolve_range
from app.modules.analysis.evidence import UTC, EvidenceRecord
from app.modules.analysis.inspector import (
    RepositoryContentSource,
    RepositoryInspector,
)
from app.modules.analysis.limits import AnalysisLimits
from app.modules.analysis.models import (
    ACTIVE,
    AnalysisEvidence,
    AnalysisJob,
    AnalysisJobEvent,
    AnalysisReport,
)
from app.modules.analysis.schemas import RepositoryAnalysisRequest
from app.modules.auth.service import get_user_github_token
from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository, user_repository
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# Lưu trữ tạm trong bộ nhớ cho phiên làm việc / PBI-015 contract
_ANALYSIS_CACHE: dict[tuple[int, str], dict[str, Any]] = {}


def now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(UTC)


# -----------------------------------------------------------------------------
# PBI-011: Background Analysis Job Transactional State Operations
# -----------------------------------------------------------------------------


def require_access(db: Session, user_id: int, repo_id: int) -> None:
    """Verify user ownership/access of repository and active GitHub token."""
    owned = db.scalar(
        select(user_repository.c.repository_id).where(
            user_repository.c.user_id == user_id,
            user_repository.c.repository_id == repo_id,
        )
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    token, _ = get_user_github_token(db, user_id)
    if not token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "GitHub access not connected")


def event(db: Session, job: AnalysisJob, code: str) -> None:
    """Record a persistent job event in ita.analysis_job_events."""
    db.add(
        AnalysisJobEvent(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            step=job.step,
            code=code,
        )
    )


def owned_job(
    db: Session, user_id: int, job_id: uuid.UUID, lock: bool = False
) -> AnalysisJob:
    """Fetch job by ID ensuring caller is the job owner."""
    stmt = select(AnalysisJob).where(
        AnalysisJob.id == job_id, AnalysisJob.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update()
    job = db.scalar(stmt)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


def active_job(
    db: Session, user_id: int, repo_id: int, scope: str
) -> AnalysisJob | None:
    """Check for an existing in-progress job for the given resource and scope."""
    return db.scalar(
        select(AnalysisJob).where(
            AnalysisJob.user_id == user_id,
            AnalysisJob.repo_id == repo_id,
            AnalysisJob.scope == scope,
            AnalysisJob.status.in_(ACTIVE),
        )
    )


def create(
    db: Session,
    user_id: int,
    repo_id: int,
    scope: str,
    retry_of: uuid.UUID | None = None,
) -> tuple[AnalysisJob, bool]:
    """Create a new analysis job if one is not already active."""
    require_access(db, user_id, repo_id)
    existing = active_job(db, user_id, repo_id, scope)
    if existing:
        return existing, False
    job = AnalysisJob(user_id=user_id, repo_id=repo_id, scope=scope, retry_of=retry_of)
    db.add(job)
    event(db, job, "created")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = active_job(db, user_id, repo_id, scope)
        if existing:
            return existing, False
        raise
    db.refresh(job)
    return job, True


def cancel(db: Session, user_id: int, job_id: uuid.UUID) -> AnalysisJob:
    """Request cancellation of an active analysis job."""
    job = owned_job(db, user_id, job_id, lock=True)
    if job.status not in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job is already terminal")
    if job.status != "cancel_requested":
        job.status = "cancel_requested"
        event(db, job, "cancel_requested")
        db.commit()
    return job


def retry(db: Session, user_id: int, job_id: uuid.UUID) -> tuple[AnalysisJob, bool]:
    """Retry a failed or cancelled analysis job."""
    old = owned_job(db, user_id, job_id, lock=True)
    if old.status not in ("failed", "cancelled"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only failed/cancelled jobs can be retried"
        )
    require_access(db, user_id, old.repo_id)
    repo_id, scope, old_id = old.repo_id, old.scope, old.id
    db.rollback()  # release lock before create()
    return create(db, user_id, repo_id, scope, retry_of=old_id)


def serialize(job: AnalysisJob) -> dict[str, Any]:
    """Serialize AnalysisJob model to JSON-safe dictionary."""
    return {
        "id": str(job.id),
        "repo_id": job.repo_id,
        "scope": job.scope,
        "status": job.status,
        "progress": job.progress,
        "step": job.step,
        "error_code": job.error_code,
        "retry_of": str(job.retry_of) if job.retry_of else None,
    }


def fail_dispatch(db: Session, job_id: uuid.UUID) -> None:
    """Persist queue failure without exposing Redis connection details."""
    job = db.scalar(
        select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
    )
    if job is not None and job.status == "queued":
        job.status = "failed"
        job.error_code = "QUEUE_UNAVAILABLE"
        job.finished_at = now()
        event(db, job, "dispatch_failed")
        db.commit()


# -----------------------------------------------------------------------------
# PBI-012: Static Code, Language, Framework & Architecture Analysis Service
# -----------------------------------------------------------------------------


class GitHubRepositoryContentSource(RepositoryContentSource):
    """Nguồn cung cấp nội dung cây thư mục và tập tin qua GitHub REST API."""

    def __init__(
        self,
        client: GitHubApiClient,
        owner: str,
        repo: str,
        commit_sha: str,
    ) -> None:
        self.client = client
        self.owner = owner
        self.repo = repo
        self.commit_sha = commit_sha

    async def get_tree_items(self) -> list[dict[str, Any]]:
        return await self.client.get_tree(
            self.owner, self.repo, self.commit_sha, recursive=True
        )

    async def get_file_content(self, path: str, max_bytes: int) -> str | None:
        return await self.client.get_file_content(
            self.owner,
            self.repo,
            path,
            ref=self.commit_sha,
            max_bytes=max_bytes,
        )


def verify_repository_access(
    db: Session,
    repository_id: int,
    user: User,
) -> Repository:
    """Kiểm tra quyền truy cập của người dùng đối với repository.

    Chỉ cho phép truy cập nếu repository thuộc sở hữu của user hoặc được liên kết
    qua bảng phân quyền user_repository.
    """
    stmt = (
        select(Repository)
        .join(
            user_repository,
            Repository.id == user_repository.c.repository_id,
        )
        .where(
            Repository.id == repository_id,
            user_repository.c.user_id == user.id,
        )
    )
    repo = db.scalar(stmt)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy repository hoặc bạn không có quyền truy cập.",
        )
    return repo


def verify_private_repo_consent(repo: Repository, scope: str | None) -> None:
    """Xác thực quyền và sự đồng thuận của người dùng đối với repository riêng tư."""
    if repo.private:
        has_private_scope = bool(scope and "repo" in scope)
        if not has_private_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Phân tích repository riêng tư yêu cầu quyền truy cập scope 'repo' "
                    "và sự đồng thuận của người dùng."
                ),
            )


async def analyze_repository(
    db: Session,
    repository_id: int,
    user: User,
    request: RepositoryAnalysisRequest,
    custom_source: RepositoryContentSource | None = None,
    client: GitHubApiClient | None = None,
    custom_commit_sha: str | None = None,
) -> dict[str, Any]:
    """Phân tích tĩnh toàn diện repository và bảo toàn bằng chứng xác thực."""
    # 1. Kiểm tra quyền truy cập repository
    repo = verify_repository_access(db, repository_id, user)

    # 2. Kiểm tra tính phù hợp của phạm vi scope được chọn
    if request.scope == "public" and repo.private:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository là riêng tư (private), không phù hợp với phạm vi phân tích 'public'.",
        )
    if request.scope == "private" and not repo.private:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository là công khai (public), không phù hợp với phạm vi phân tích 'private'.",
        )

    # 3. Kiểm tra token và quyền scope private
    token, scope = get_user_github_token(db, user.id)
    verify_private_repo_consent(repo, scope)

    # 4. Xử lý khoảng thời gian (PBI-010) nếu có
    time_range_info = None
    target_until = None
    if request.mode:
        start_utc, end_utc = resolve_range(
            mode=request.mode,
            preset=request.preset,
            month=request.month,
            start_date=request.start_date,
            end_date=request.end_date,
            timezone_name=request.timezone,
        )
        time_range_info = {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "timezone": request.timezone,
        }
        target_until = end_utc

    # 5. Khởi tạo content source và xác định commit SHA
    commit_sha = custom_commit_sha or "0000000000000000000000000000000000000000"
    content_source = custom_source

    if content_source is None:
        owner = repo.full_name.split("/")[0] if "/" in repo.full_name else repo.name
        repo_name = repo.full_name.split("/")[1] if "/" in repo.full_name else repo.name

        api_client = client or GitHubApiClient(access_token=token)
        try:
            latest_sha = await api_client.get_latest_commit_sha(
                owner=owner,
                repo=repo_name,
                branch=repo.default_branch or "main",
                until=target_until,
            )
            if latest_sha:
                commit_sha = latest_sha
        except (
            GitHubPermissionError,
            GitHubTokenRevokedError,
            GitHubRateLimitError,
            GitHubApiError,
        ) as exc:
            logger.warning(
                "Không thể lấy commit SHA mới nhất qua GitHub API: %s. Dùng fallback SHA.",
                exc,
            )

        content_source = GitHubRepositoryContentSource(
            client=api_client,
            owner=owner,
            repo=repo_name,
            commit_sha=commit_sha,
        )

    # 6. Khởi tạo và thực thi RepositoryInspector
    limits = AnalysisLimits()
    inspector = RepositoryInspector(
        repository_id=repo.id,
        commit_sha=commit_sha,
        limits=limits,
        scope=request.scope,
        time_range=time_range_info,
    )

    result = await inspector.inspect(
        source=content_source,
        github_languages=repo.languages,
    )

    # 7. Lưu trữ kết quả và bằng chứng xác thực vào DB và cache
    save_analysis_result(db, result)

    return result


def save_analysis_result(db: Session, result: dict[str, Any]) -> AnalysisReport | None:
    """Save an analysis result and its verifiable evidence records to PostgreSQL and L1 cache."""
    cache_key = (result["repository_id"], result["commit_sha"])
    _ANALYSIS_CACHE[cache_key] = result

    try:
        analyzed_at_val = result.get("analyzed_at")
        if isinstance(analyzed_at_val, str):
            analyzed_dt = datetime.fromisoformat(analyzed_at_val)
        elif isinstance(analyzed_at_val, datetime):
            analyzed_dt = analyzed_at_val
        else:
            analyzed_dt = now()

        report = AnalysisReport(
            repository_id=result["repository_id"],
            commit_sha=result["commit_sha"],
            analyzed_at=analyzed_dt,
            scope=result.get("scope", "all"),
            time_range=result.get("time_range"),
            structure=result.get("structure", {}),
            languages=result.get("languages", []),
            frameworks=result.get("frameworks", []),
            architecture=result.get("architecture", []),
            budget=result.get("budget", {}),
        )
        db.add(report)
        db.flush()

        evidence_items = result.get("evidence", [])
        for e in evidence_items:
            e_dict = e if isinstance(e, dict) else e.model_dump()
            ev_rec = AnalysisEvidence(
                report_id=report.id,
                repository_id=result["repository_id"],
                commit_sha=result["commit_sha"],
                file_path=e_dict.get("file_path", ""),
                finding_type=e_dict.get("finding_type", "structure"),
                classification=e_dict.get("classification", ""),
                evidence_source=e_dict.get("evidence_source", "metadata"),
                detection_method=e_dict.get("detection_method", "metadata_extraction"),
                confidence=e_dict.get("confidence", "high"),
                confidence_score=float(e_dict.get("confidence_score", 1.0)),
                rationale=e_dict.get("rationale", ""),
                line_number=e_dict.get("line_number"),
                matched_content=e_dict.get("matched_content"),
                scope=e_dict.get("scope", result.get("scope", "all")),
                time_range=e_dict.get("time_range", result.get("time_range")),
            )
            db.add(ev_rec)

        db.commit()
        return report
    except (SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Could not persist analysis report to database: %s", exc)
        db.rollback()
        return None


def get_latest_analysis(
    db: Session,
    repository_id: int,
    user: User,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Lấy kết quả phân tích gần nhất đã lưu trong DB hoặc phiên."""
    verify_repository_access(db, repository_id, user)

    # 1. Kiểm tra bộ nhớ đệm (L1 cache)
    if commit_sha:
        cache_key = (repository_id, commit_sha)
        if cache_key in _ANALYSIS_CACHE:
            return _ANALYSIS_CACHE[cache_key]
    else:
        matching = [
            res for (r_id, _), res in _ANALYSIS_CACHE.items() if r_id == repository_id
        ]
        if matching:
            matching.sort(key=lambda r: r.get("analyzed_at", ""), reverse=True)
            return matching[0]

    # 2. Truy vấn từ cơ sở dữ liệu PostgreSQL nếu cache chưa có
    try:
        stmt = select(AnalysisReport).where(
            AnalysisReport.repository_id == repository_id
        )
        if commit_sha:
            stmt = stmt.where(AnalysisReport.commit_sha == commit_sha)
        stmt = stmt.order_by(AnalysisReport.analyzed_at.desc())
        report = db.scalar(stmt)
        if report:
            ev_stmt = select(AnalysisEvidence).where(
                AnalysisEvidence.report_id == report.id
            )
            ev_rows = db.scalars(ev_stmt).all()
            evidence_list = [
                {
                    "repository_id": ev.repository_id,
                    "commit_sha": ev.commit_sha,
                    "file_path": ev.file_path,
                    "finding_type": ev.finding_type,
                    "classification": ev.classification,
                    "evidence_source": ev.evidence_source,
                    "detection_method": ev.detection_method,
                    "confidence": ev.confidence,
                    "confidence_score": ev.confidence_score,
                    "rationale": ev.rationale,
                    "line_number": ev.line_number,
                    "matched_content": ev.matched_content,
                    "scope": ev.scope,
                    "time_range": ev.time_range,
                    "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                }
                for ev in ev_rows
            ]
            result = {
                "repository_id": report.repository_id,
                "commit_sha": report.commit_sha,
                "analyzed_at": (
                    report.analyzed_at.isoformat() if report.analyzed_at else ""
                ),
                "scope": report.scope,
                "time_range": report.time_range,
                "structure": report.structure,
                "languages": report.languages,
                "frameworks": report.frameworks,
                "architecture": report.architecture,
                "evidence": evidence_list,
                "evidence_count": len(evidence_list),
                "budget": report.budget,
            }
            _ANALYSIS_CACHE[(report.repository_id, report.commit_sha)] = result
            return result
    except (SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Error fetching analysis report from database: %s", exc)

    if commit_sha:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy kết quả phân tích cho commit SHA: {commit_sha}",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Repository chưa được phân tích. Vui lòng kích hoạt phân tích trước.",
    )


def get_analysis_evidence(
    db: Session,
    repository_id: int,
    user: User,
    commit_sha: str | None = None,
) -> list[EvidenceRecord]:
    """Truy xuất danh sách bằng chứng được liên kết với commit hash chính xác."""
    analysis = get_latest_analysis(db, repository_id, user, commit_sha=commit_sha)
    evidence_dicts = analysis.get("evidence", [])
    return [EvidenceRecord.model_validate(e) for e in evidence_dicts]
