"""GitHub OAuth authentication routes."""

import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.api.dependencies import SESSION_COOKIE, get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.modules.auth.github import GitHubOAuthError, get_github_identity
from app.modules.auth.service import (
    SESSION_TTL_SECONDS,
    GitHubAccountConflictError,
    consume_oauth_access_mode,
    consume_oauth_state,
    create_oauth_state,
    create_session,
    disconnect_github,
    get_or_create_github_user,
    revoke_session,
)
from app.modules.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

OAUTH_STATE_COOKIE = "github_oauth_state"
OAUTH_BROWSER_COOKIE = "github_oauth_browser"


OAUTH_STATE_COOKIE_MAX_AGE = 300

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


def _clear_oauth_cookies(response: RedirectResponse) -> None:
    """Xóa cookie OAuth sau khi callback xử lý xong."""

    secure_cookie = settings.app_env == "production"

    response.delete_cookie(
        key=OAUTH_BROWSER_COOKIE,
        path="/api/v1/auth",
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
    )

    response.delete_cookie(
        key=OAUTH_STATE_COOKIE,
        path="/api/v1/auth",
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
    )


def _frontend_redirect(error: str | None = None) -> RedirectResponse:
    """Chuyển người dùng về frontend với mã lỗi an toàn."""

    target = f"{settings.frontend_url.rstrip('/')}/"

    if error:
        target = f"{target}?{urlencode({'auth_error': error})}"

    response = RedirectResponse(
        url=target,
        status_code=status.HTTP_303_SEE_OTHER,
    )

    _clear_oauth_cookies(response)

    return response


@router.get("/github")
def github_login(include_private: bool = False) -> RedirectResponse:
    """Redirect the user to GitHub OAuth authorization.

    Nếu `include_private=True`, yêu cầu thêm quyền `repo` để đồng bộ private
    repositories.
    """

    if not settings.github_oauth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth chưa được cấu hình.",
        )

    browser_binding = secrets.token_urlsafe(32)
    access_mode = "private_enabled" if include_private else "public_only"
    try:
        state = create_oauth_state(browser_binding, access_mode=access_mode)
    except TypeError:
        state = create_oauth_state(browser_binding)

    scope = "read:user user:email repo" if include_private else "read:user user:email"

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": scope,
        "state": state,
    }

    authorization_url = f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    response = RedirectResponse(
        url=authorization_url,
        status_code=status.HTTP_302_FOUND,
    )

    secure_cookie = settings.app_env == "production"

    response.set_cookie(
        key=OAUTH_BROWSER_COOKIE,
        value=browser_binding,
        max_age=OAUTH_STATE_COOKIE_MAX_AGE,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/api/v1/auth",
    )

    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=OAUTH_STATE_COOKIE_MAX_AGE,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/api/v1/auth",
    )

    return response


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_session),  # noqa: B008
) -> RedirectResponse:
    """Xử lý GitHub callback và tạo phiên đăng nhập."""

    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE)
    browser_binding = request.cookies.get(OAUTH_BROWSER_COOKIE)

    # Kiểm tra state và cookie trước khi tiêu thụ state trong Redis.
    if (
        not state
        or not cookie_state
        or not browser_binding
        or not secrets.compare_digest(state, cookie_state)
    ):
        return _frontend_redirect("oauth_state_invalid")

    # State chỉ được sử dụng một lần và phải thuộc đúng trình duyệt.
    if not consume_oauth_state(state, browser_binding):
        return _frontend_redirect("oauth_state_invalid")

    access_mode = consume_oauth_access_mode(state)

    # Người dùng từ chối cấp quyền trên GitHub.
    if error:
        return _frontend_redirect("github_access_denied")

    if not code:
        return _frontend_redirect("github_login_failed")

    try:
        identity = await get_github_identity(code)

        try:
            user = get_or_create_github_user(db, identity, access_mode=access_mode)
        except TypeError:
            user = get_or_create_github_user(db, identity)

        session_id = create_session(user.id)

    except GitHubAccountConflictError:
        return _frontend_redirect("github_account_conflict")

    except (GitHubOAuthError, ValueError):
        return _frontend_redirect("github_login_failed")

    except Exception:
        logger.exception("GitHub OAuth callback failed")
        return _frontend_redirect("github_login_failed")

    response = RedirectResponse(
        url=f"{settings.frontend_url.rstrip('/')}/",
        status_code=status.HTTP_303_SEE_OTHER,
    )

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )

    _clear_oauth_cookies(response)

    return response


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> dict:
    """Lấy thông tin người dùng đang đăng nhập."""

    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
    }


@router.post("/github/disconnect")
def disconnect_github_account(
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_session),  # noqa: B008
) -> dict:
    """Hủy liên kết tài khoản GitHub và xóa token đã lưu."""

    disconnected = disconnect_github(db, current_user.id)

    return {
        "disconnected": disconnected,
        "message": (
            "Đã hủy liên kết GitHub thành công."
            if disconnected
            else "Chưa liên kết GitHub."
        ),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
) -> Response:
    """Đăng xuất và thu hồi session hiện tại."""

    origin = request.headers.get("origin")

    if origin not in settings.cors_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin không được phép.",
        )

    session_id = request.cookies.get(SESSION_COOKIE)

    try:
        revoke_session(session_id)
    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể đăng xuất lúc này. Vui lòng thử lại.",
        ) from None

    response = Response(status_code=status.HTTP_204_NO_CONTENT)

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )

    return response
