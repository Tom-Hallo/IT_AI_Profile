"""Service layer for repository analysis, authorization, evidence preservation, and
background job state (PBI-011 & PBI-012).
"""

from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from contextlib import AsyncExitStack, nullcontext
from datetime import datetime
from threading import Lock
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
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
from app.modules.auth.service import get_user_github_token, has_private_access
from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
    GitHubEmptyRepositoryError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository, user_repository
from app.modules.users.models import User

logger = logging.getLogger(__name__)


# Cached evidence is used only after the database resolves the exact report.
_ANALYSIS_CACHE_LIMIT = 32
_ANALYSIS_CACHE_LOCK = Lock()
_ANALYSIS_CACHE: OrderedDict[
    tuple[int, str, str, str, str, str],
    dict[str, Any],
] = OrderedDict()


def _analysis_cache_key(
    result: dict[str, Any],
) -> tuple[int, str, str, str, str, str]:
    time_range = result.get("time_range") or {}

    return (
        result["repository_id"],
        result["commit_sha"],
        result.get("scope", "all"),
        time_range.get("start_utc") or "",
        time_range.get("end_utc") or "",
        time_range.get("timezone") or "",
    )


def cache_analysis_result(result: dict[str, Any]) -> None:
    """Cập nhật cache sau khi transaction đã commit thành công."""
    key = _analysis_cache_key(result)
    with _ANALYSIS_CACHE_LOCK:
        _ANALYSIS_CACHE[key] = {
            "report_id": result["report_id"],
            "evidence": result["evidence"],
        }
        _ANALYSIS_CACHE.move_to_end(key)
        if len(_ANALYSIS_CACHE) > _ANALYSIS_CACHE_LIMIT:
            _ANALYSIS_CACHE.popitem(last=False)


def clear_user_analysis_cache(db: Session, user_id: int) -> None:
    """Xóa toàn bộ bản ghi cache trong bộ nhớ liên quan đến các repo của user."""
    repo_ids = set(
        db.scalars(
            select(user_repository.c.repository_id).where(
                user_repository.c.user_id == user_id
            )
        ).all()
    )
    with _ANALYSIS_CACHE_LOCK:
        keys_to_delete = [k for k in _ANALYSIS_CACHE if k[0] in repo_ids]
        for key in keys_to_delete:
            _ANALYSIS_CACHE.pop(key, None)


def now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(UTC)


# -----------------------------------------------------------------------------
# PBI-011: Background Analysis Job Transactional State Operations
# -----------------------------------------------------------------------------


def require_access(db: Session, user_id: int, repo_id: int) -> None:
    """Verify user ownership/access of repository and active GitHub token."""
    repo = db.scalar(
        select(Repository)
        .join(user_repository, Repository.id == user_repository.c.repository_id)
        .where(
            user_repository.c.user_id == user_id,
            user_repository.c.repository_id == repo_id,
        )
    )
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    if getattr(repo, "private", False) and not has_private_access(db, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    token, _ = get_user_github_token(db, user_id)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub access not connected")
    if getattr(repo, "private", False):
        from app.modules.consent.guards import require_private_access_consent

        require_private_access_consent(db, user_id, repo_id)


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
    *,
    request_options: dict[str, Any] | None = None,
    commit: bool = True,
) -> tuple[AnalysisJob, bool]:
    """Create or reuse a job. With commit=False, the caller owns the transaction."""
    require_access(db, user_id, repo_id)

    def reuse(existing: AnalysisJob) -> tuple[AnalysisJob, bool]:
        if (existing.request_options or {}) != (request_options or {}):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Repository đang có một phân tích với bộ lọc khác.",
            )
        return existing, False

    existing = active_job(db, user_id, repo_id, scope)
    if existing:
        return reuse(existing)
    job = AnalysisJob(
        user_id=user_id,
        repo_id=repo_id,
        scope=scope,
        retry_of=retry_of,
        request_options=request_options,
    )
    try:
        with nullcontext() if commit else db.begin_nested():
            db.add(job)
            db.flush()
            event(db, job, "created")
        if commit:
            db.commit()
    except IntegrityError:
        if commit:
            db.rollback()
        existing = active_job(db, user_id, repo_id, scope)
        if existing:
            return reuse(existing)
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
    request_options = old.request_options
    db.rollback()  # release lock before create()
    return create(
        db, user_id, repo_id, scope, retry_of=old_id, request_options=request_options
    )


def serialize(job: AnalysisJob) -> dict[str, Any]:
    """Serialize AnalysisJob model to JSON-safe dictionary."""
    return {
        "id": str(job.id),
        "repo_id": job.repo_id,
        "report_id": job.report_id,
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
        self.tree_truncated = False

    async def get_tree_items(self) -> list[dict[str, Any]]:
        return await self.client.get_tree(
            self.owner, self.repo, self.commit_sha, on_truncated=self._mark_truncated
        )

    def _mark_truncated(self) -> None:
        self.tree_truncated = True

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
    qua bảng phân quyền user_repository, và thỏa mãn server-authoritative private
    access.
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
    if repo.private and not has_private_access(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy repository hoặc bạn không có quyền truy cập.",
        )
    return repo


def verify_private_repo_consent(
    repo: Repository,
    scope: str | None,
    db: Session | None = None,
    user_id: int | None = None,
) -> None:
    """Xác thực quyền và sự đồng thuận của người dùng đối với repository riêng tư."""
    if repo.private:
        if db is not None and user_id is not None:
            if not has_private_access(db, user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Phân tích repository riêng tư yêu cầu quyền truy cập private "
                        "đã được kích hoạt và token có scope 'repo'."
                    ),
                )
            from app.modules.consent.guards import require_private_access_consent

            require_private_access_consent(db, user_id, repo.id)
        else:
            has_private_scope = bool(scope and "repo" in scope)
            if not has_private_scope:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Phân tích repository riêng tư yêu cầu quyền truy cập scope "
                        "'repo' và sự đồng thuận của người dùng."
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
            detail=(
                "Repository là riêng tư (private), không phù hợp "
                "với phạm vi phân tích 'public'."
            ),
        )
    if request.scope == "private" and not repo.private:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Repository là công khai (public), không phù hợp "
                "với phạm vi phân tích 'private'."
            ),
        )

    # 3. Kiểm tra token và quyền scope private
    token, scope = get_user_github_token(db, user.id)
    verify_private_repo_consent(repo, scope, db=db, user_id=user.id)

    # 4. Xử lý khoảng thời gian (PBI-010) nếu có
    time_range_info = None
    target_until = None
    if request.mode:
        start_utc, end_utc = resolve_range(
            mode=request.mode,
            preset=request.preset,
            month=request.month,
            year=request.year,
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

    commit_sha = custom_commit_sha or "0000000000000000000000000000000000000000"
    content_source = custom_source

    try:
        async with AsyncExitStack() as resources:
            if content_source is None:
                if not token and client is None:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Vui lòng liên kết lại tài khoản GitHub để phân tích.",
                    )

                owner, _, repo_name = repo.full_name.partition("/")
                repo_name = repo_name or repo.name
                api_client = client
                if api_client is None:
                    api_client = await resources.enter_async_context(
                        GitHubApiClient(access_token=token)
                    )
                target_branch = request.branch or repo.default_branch or "main"
                latest_sha = await api_client.get_latest_commit_sha(
                    owner=owner,
                    repo=repo_name,
                    branch_or_ref=target_branch,
                    until=target_until,
                )
                if not latest_sha:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Không tìm thấy commit trên nhánh trong khoảng đã chọn.",
                    )

                commit_sha = latest_sha
                content_source = GitHubRepositoryContentSource(
                    client=api_client,
                    owner=owner,
                    repo=repo_name,
                    commit_sha=commit_sha,
                )

            inspector = RepositoryInspector(
                repository_id=repo.id,
                commit_sha=commit_sha,
                limits=AnalysisLimits(),
                scope=request.scope,
                time_range=time_range_info,
            )
            result = await inspector.inspect(
                source=content_source,
                github_languages=repo.languages,
            )
    except GitHubTokenRevokedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub từ chối token. Vui lòng liên kết lại tài khoản GitHub.",
        ) from exc
    except GitHubPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except GitHubNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except GitHubEmptyRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except GitHubApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    # 7. Lưu trữ kết quả và bằng chứng xác thực vào DB và cache
    if repo.private:
        db.scalar(select(Repository).where(Repository.id == repo.id).with_for_update())
        verify_private_repo_consent(repo, scope, db=db, user_id=user.id)
        redact_private_evidence(result)
    report = save_analysis_result(db, result)

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể lưu kết quả phân tích.",
        )

    try:
        from app.modules.analysis.schemas import VerificationRequest
        from app.modules.analysis.verification_service import (
            get_verification_summary,
            verify_repository_contributions,
        )

        verif_res = await verify_repository_contributions(
            db=db,
            repository_id=repository_id,
            user=user,
            client=api_client if custom_source is None else None,
            report_id=report.id,
            request=VerificationRequest(
                scope=request.scope
                if request.scope in ("public", "private")
                else "all",
                **request.model_dump(exclude={"scope"}),
            ),
        )
        if verif_res:
            v_summary = get_verification_summary(
                db, repository_id, user, report_id=report.id
            )
            if v_summary:
                result["verification"] = v_summary.model_dump()
    except Exception as ve:
        logger.warning("Không thể xác minh đóng góp: %s", type(ve).__name__)

    return result


def redact_private_evidence(result: dict[str, Any]) -> None:
    """Drop source excerpts before a private report is persisted."""
    for evidence in result.get("evidence", []):
        evidence["matched_content"] = None


def save_analysis_result(
    db: Session,
    result: dict[str, Any],
    *,
    commit: bool = True,
) -> AnalysisReport | None:
    """Save an analysis result and its verifiable evidence records to PostgreSQL and L1
    cache.
    """

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

        db.flush()
        from app.modules.analysis.finding_service import build_findings

        build_findings(db, report)

        if commit:
            db.commit()
        else:
            db.flush()

        result["report_id"] = report.id
        if commit and "evidence" in result:
            cache_analysis_result(result)

        return report

    except (SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
        db.rollback()
        logger.error(
            "Failed to persist repository analysis report",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể lưu kết quả phân tích. Vui lòng thử lại.",
        ) from exc


def get_latest_analysis(
    db: Session,
    repository_id: int,
    user: User,
    commit_sha: str | None = None,
    report_id: int | None = None,
    *,
    include_evidence: bool = True,
) -> dict[str, Any]:
    """Resolve the latest snapshot in PostgreSQL, then load its evidence."""
    repo = verify_repository_access(db, repository_id, user)
    verify_private_repo_consent(repo, None, db=db, user_id=user.id)

    try:
        stmt = select(AnalysisReport).where(
            AnalysisReport.repository_id == repository_id
        )
        if commit_sha:
            stmt = stmt.where(AnalysisReport.commit_sha == commit_sha)

        if report_id is not None:
            stmt = stmt.where(AnalysisReport.id == report_id)

        stmt = stmt.order_by(
            AnalysisReport.analyzed_at.desc(),
            AnalysisReport.id.desc(),
        )
        report = db.scalar(stmt.limit(1))
        if report:
            ev_stmt = select(AnalysisEvidence).where(
                AnalysisEvidence.report_id == report.id
            )
            key = _analysis_cache_key(
                {
                    "repository_id": repository_id,
                    "commit_sha": report.commit_sha,
                    "scope": report.scope,
                    "time_range": report.time_range,
                }
            )
            with _ANALYSIS_CACHE_LOCK:
                cached = _ANALYSIS_CACHE.get(key)
            cached_evidence = (
                cached["evidence"]
                if include_evidence and cached and cached["report_id"] == report.id
                else None
            )
            ev_rows = (
                db.scalars(ev_stmt.order_by(AnalysisEvidence.id)).all()
                if include_evidence and cached_evidence is None
                else []
            )
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
                    "matched_content": None if repo.private else ev.matched_content,
                    "scope": ev.scope,
                    "time_range": ev.time_range,
                    "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                }
                for ev in ev_rows
            ]
            if cached_evidence is not None:
                evidence_list = [dict(item) for item in cached_evidence]
            if repo.private:
                for item in evidence_list:
                    item["matched_content"] = None
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
                "evidence_count": (
                    len(evidence_list)
                    if include_evidence
                    else db.scalar(select(func.count()).select_from(ev_stmt.subquery()))
                ),
                "budget": report.budget,
            }
            try:
                from app.modules.analysis.verification_service import (
                    get_verification_summary,
                )

                verif_summary = get_verification_summary(
                    db, repository_id, user, report_id=report.id
                )
                if verif_summary:
                    result["verification"] = verif_summary.model_dump()
            except Exception:
                pass
            result["report_id"] = report.id
            if include_evidence and cached_evidence is None:
                cache_analysis_result(result)
            return result
    except (SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Error fetching analysis report: %s", type(exc).__name__)
        raise HTTPException(503, "Không thể đọc báo cáo phân tích.") from exc

    if commit_sha or report_id is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bản phân tích được yêu cầu.",
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
    report_id: int | None = None,
) -> list[EvidenceRecord]:
    """Truy xuất evidence của đúng repository, commit hoặc report."""

    analysis = get_latest_analysis(
        db,
        repository_id,
        user,
        commit_sha=commit_sha,
        report_id=report_id,
    )

    evidence_dicts = analysis.get("evidence", [])

    return [EvidenceRecord.model_validate(e) for e in evidence_dicts]
