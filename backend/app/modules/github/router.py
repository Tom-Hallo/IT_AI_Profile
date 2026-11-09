"""API routes cho GitHub repository synchronization (PBI-009)."""

from __future__ import annotations

import logging
import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.modules.auth.service import get_user_github_token
from app.modules.github.client import (
    GitHubApiError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
)
from app.modules.github.models import Repository, user_repository
from app.modules.github.schemas import (
    RepositoryItemResponse,
    RepositoryListResponse,
    SyncStatusResponse,
    SyncTriggerResponse,
)
from app.modules.github.service import (
    get_user_sync_status,
    set_sync_status_cache,
    sync_repositories_for_user,
)
from app.modules.users.models import User
from app.workers.enqueue import enqueue_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["GitHub Synchronization"])


@router.post(
    "/sync",
    response_model=SyncTriggerResponse,
    status_code=status.HTTP_200_OK,
)
async def trigger_repository_sync(
    background: bool = Query(
        default=True,
        description="Chạy tác vụ trong nền với RQ (mặc định: True)",
    ),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SyncTriggerResponse:
    """Kích hoạt tiến trình đồng bộ GitHub repositories cho người dùng hiện tại."""

    token, _ = get_user_github_token(db, current_user.id)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Tài khoản chưa kết nối GitHub hoặc token đã hết hạn. "
                "Vui lòng đăng nhập lại qua GitHub."
            ),
        )

    current_status = get_user_sync_status(db, current_user.id)
    if current_status["status"] == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tiến trình đồng bộ đang chạy. Vui lòng đợi trong giây lát.",
        )

    if background:
        try:
            job = enqueue_task(
                "app.workers.tasks.sync_repositories.sync_user_repositories_task",
                current_user.id,
                job_timeout=settings.github_sync_timeout_seconds,
            )
            set_sync_status_cache(
                current_user.id,
                status="running",
                job_id=job.id,
            )
            return SyncTriggerResponse(
                status="running",
                message="Tiến trình đồng bộ đã được đưa vào hàng đợi xử lý.",
                job_id=job.id,
            )
        except (RedisError, OSError, TimeoutError) as exc:
            logger.warning(
                f"Không thể đưa vào hàng đợi RQ ({exc}), chuyển sang thực thi đồng bộ trực tiếp."
            )

    try:
        result = await sync_repositories_for_user(db, current_user)
        return SyncTriggerResponse(
            status="completed",
            message="Đồng bộ repositories thành công.",
            synced_count=result.get("synced_count"),
            last_synced_at=result.get("last_synced_at"),
        )
    except GitHubTokenRevokedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from None
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from None
    except GitHubPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from None
    except GitHubApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from None


@router.get("/sync/status", response_model=SyncStatusResponse)
def get_sync_status(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> SyncStatusResponse:
    """Lấy trạng thái tiến trình đồng bộ và thống kê repository của người dùng."""
    status_info = get_user_sync_status(db, current_user.id)
    return SyncStatusResponse(**status_info)


@router.get("/repositories", response_model=RepositoryListResponse)
def list_user_repositories(
    page: int = Query(default=1, ge=1, description="Số trang (bắt đầu từ 1)"),
    per_page: int = Query(default=20, ge=1, le=100, description="Số bản ghi mỗi trang"),
    visibility: Literal["all", "public", "private"] = Query(
        default="all", description="Lọc theo phạm vi repository"
    ),
    search: str | None = Query(
        default=None, description="Tìm kiếm theo tên hoặc mô tả"
    ),
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> RepositoryListResponse:
    """Lấy danh sách repositories đã đồng bộ thuộc quyền truy cập của người dùng."""

    base_query = (
        select(Repository)
        .join(
            user_repository,
            Repository.id == user_repository.c.repository_id,
        )
        .where(user_repository.c.user_id == current_user.id)
    )

    if visibility == "public":
        base_query = base_query.where(Repository.private.is_(False))
    elif visibility == "private":
        base_query = base_query.where(Repository.private.is_(True))

    if search and search.strip():
        search_pattern = f"%{search.strip()}%"
        base_query = base_query.where(
            or_(
                Repository.name.ilike(search_pattern),
                Repository.full_name.ilike(search_pattern),
                Repository.description.ilike(search_pattern),
            )
        )

    # Đếm tổng số bản ghi phù hợp
    count_query = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(count_query) or 0

    total_pages = math.ceil(total / per_page) if total > 0 else 1

    # Phân trang và sắp xếp theo cập nhật mới nhất
    offset = (page - 1) * per_page
    query = (
        base_query.order_by(
            Repository.pushed_at.desc().nullslast(),
            Repository.updated_at.desc(),
        )
        .offset(offset)
        .limit(per_page)
    )

    repositories = db.scalars(query).all()

    return RepositoryListResponse(
        items=[RepositoryItemResponse.model_validate(r) for r in repositories],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/repositories/{repository_id}", response_model=RepositoryItemResponse)
def get_user_repository(
    repository_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> RepositoryItemResponse:
    """Lấy thông tin chi tiết một repository, kiểm tra nghiêm ngặt quyền truy cập của user."""

    stmt = (
        select(Repository)
        .join(
            user_repository,
            Repository.id == user_repository.c.repository_id,
        )
        .where(
            Repository.id == repository_id,
            user_repository.c.user_id == current_user.id,
        )
    )

    repo = db.scalar(stmt)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy repository hoặc bạn không có quyền truy cập.",
        )

    return RepositoryItemResponse.model_validate(repo)
