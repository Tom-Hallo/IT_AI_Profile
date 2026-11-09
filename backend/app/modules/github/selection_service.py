"""PBI-006 selection logic; never trust repository identifiers from browsers."""

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.auth.service import get_user_github_token
from app.modules.github.client import (
    GitHubApiClient,
    GitHubApiError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubTokenRevokedError,
    _parse_next_link,
)
from app.modules.github.selection_models import (
    RepositorySelection,
    RepositorySelectionSetting,
)
from app.modules.github.selection_schemas import (
    OptionsResponse,
    RepoOption,
    Scope,
    SelectionResponse,
    SelectionUpdate,
)


def matches_scope(repo: RepoOption, scope: Scope) -> bool:
    return scope == "combined" or (
        repo.private if scope == "private" else not repo.private
    )


def credentials(db: Session, user_id: int) -> tuple[str, bool]:
    token, scopes = get_user_github_token(db, user_id)
    if not token:
        raise HTTPException(401, "Vui lòng kết nối lại tài khoản GitHub.")
    return token, "repo" in set((scopes or "").replace(",", " ").split())


async def fetch_options(token: str) -> list[RepoOption]:
    try:
        client = GitHubApiClient(token)
        raw = []
        next_url = "/user/repos"
        params = {
            "per_page": 100,
            "affiliation": "owner,collaborator,organization_member",
        }
        for _ in range(100):
            response = await client._request("GET", next_url, params=params)
            page = response.json()
            if not isinstance(page, list):
                raise GitHubApiError("Invalid repository listing")
            raw.extend(page)
            next_url = _parse_next_link(response.headers.get("link"))
            if not next_url:
                break
            params = None
        else:
            raise GitHubApiError("Repository listing exceeds page limit")
        return [RepoOption.model_validate(item) for item in raw]
    except GitHubTokenRevokedError:
        raise HTTPException(401, "GitHub token đã hết hạn hoặc bị thu hồi.") from None
    except GitHubRateLimitError:
        raise HTTPException(
            429, "GitHub API rate limit. Vui lòng thử lại sau."
        ) from None
    except GitHubPermissionError:
        raise HTTPException(403, "GitHub từ chối quyền truy cập.") from None
    except (GitHubApiError, ValueError, TypeError):
        raise HTTPException(502, "Không thể xác minh danh sách repository.") from None


async def options(db: Session, user_id: int, scope: Scope) -> OptionsResponse:
    token, private_access = credentials(db, user_id)
    if scope == "private" and not private_access:
        raise HTTPException(403, "Cần cấp quyền repo để truy cập private repositories.")
    repos = await fetch_options(token)
    return OptionsResponse(
        scope=scope,
        private_access_granted=private_access,
        items=[
            r
            for r in repos
            if matches_scope(r, scope) and (not r.private or private_access)
        ],
    )


def read_selection(db: Session, user_id: int) -> SelectionResponse:
    setting = db.get(RepositorySelectionSetting, user_id)
    ids = db.scalars(
        select(RepositorySelection.github_repository_id)
        .where(RepositorySelection.user_id == user_id)
        .order_by(RepositorySelection.github_repository_id)
    ).all()
    return SelectionResponse(
        scope=setting.scope if setting else "public", repository_ids=list(ids)
    )


async def update_selection(
    db: Session, user_id: int, payload: SelectionUpdate
) -> SelectionResponse:
    ids = payload.repository_ids
    if len(ids) != len(set(ids)) or any(r <= 0 for r in ids):
        raise HTTPException(422, "Repository ID trùng hoặc không hợp lệ.")
    token, private_access = credentials(db, user_id)
    if payload.scope == "private" and not private_access:
        raise HTTPException(403, "Cần cấp quyền repo để chọn private repositories.")
    available = {r.id: r for r in await fetch_options(token)}
    for repo_id in ids:
        repo = available.get(repo_id)
        if repo is None:
            raise HTTPException(403, "Repository không thuộc quyền truy cập.")
        if not matches_scope(repo, payload.scope):
            raise HTTPException(422, "Repository nằm ngoài scope đã chọn.")
        if repo.private and not private_access:
            raise HTTPException(403, "Thiếu quyền private repository.")
    setting = db.get(RepositorySelectionSetting, user_id)
    if setting is None:
        db.add(RepositorySelectionSetting(user_id=user_id, scope=payload.scope))
    else:
        setting.scope = payload.scope
    try:
        db.execute(
            delete(RepositorySelection).where(RepositorySelection.user_id == user_id)
        )
        db.add_all(
            RepositorySelection(user_id=user_id, github_repository_id=repo_id)
            for repo_id in ids
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return SelectionResponse(scope=payload.scope, repository_ids=ids)
