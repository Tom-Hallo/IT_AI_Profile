"""Service layer for repository analysis, authorization, and evidence preservation (PBI-012)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time_range import resolve_range
from app.modules.analysis.evidence import EvidenceRecord
from app.modules.analysis.inspector import (
    RepositoryContentSource,
    RepositoryInspector,
)
from app.modules.analysis.limits import AnalysisLimits
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
    commit_sha = "0000000000000000000000000000000000000000"
    content_source = custom_source

    if content_source is None:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tài khoản chưa kết nối GitHub hoặc token đã hết hạn.",
            )
        gh_client = client or GitHubApiClient(token)

        owner = (
            repo.full_name.split("/")[0]
            if repo.full_name and "/" in repo.full_name
            else repo.name
        )
        repo_name = (
            repo.full_name.split("/")[1]
            if repo.full_name and "/" in repo.full_name
            else repo.name
        )

        try:
            fetched_sha = await gh_client.get_latest_commit_sha(
                owner=owner,
                repo=repo_name,
                branch_or_ref=repo.default_branch or "main",
                until=target_until,
            )
            if fetched_sha:
                commit_sha = fetched_sha
        except (
            GitHubApiError,
            GitHubPermissionError,
            GitHubRateLimitError,
            GitHubTokenRevokedError,
        ) as exc:
            logger.warning(f"Không thể lấy commit SHA từ GitHub: {exc}")

        content_source = GitHubRepositoryContentSource(
            client=gh_client,
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

    # 7. Lưu trữ cache kết quả và bằng chứng phục vụ truy xuất sau này
    cache_key = (repo.id, commit_sha)
    _ANALYSIS_CACHE[cache_key] = result

    return result


def get_latest_analysis(
    db: Session,
    repository_id: int,
    user: User,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Lấy kết quả phân tích gần nhất đã lưu trong phiên."""
    verify_repository_access(db, repository_id, user)

    # Nếu có commit_sha cụ thể
    if commit_sha:
        cache_key = (repository_id, commit_sha)
        if cache_key in _ANALYSIS_CACHE:
            return _ANALYSIS_CACHE[cache_key]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy kết quả phân tích cho commit SHA: {commit_sha}",
        )

    # Tìm phân tích mới nhất của repository
    matching = [
        res for (r_id, _), res in _ANALYSIS_CACHE.items() if r_id == repository_id
    ]
    if not matching:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository chưa được phân tích. Vui lòng kích hoạt phân tích trước.",
        )

    # Sắp xếp theo analyzed_at mới nhất
    matching.sort(key=lambda r: r.get("analyzed_at", ""), reverse=True)
    return matching[0]


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
