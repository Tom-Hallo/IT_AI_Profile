"""Redis services for GitHub OAuth state and application sessions."""

import secrets

from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.redis import get_redis_connection
from app.modules.auth.github import GitHubIdentity
from app.modules.auth.models import OAuthAccount
from app.modules.users.models import User

# OAuth state tồn tại 5 phút.
OAUTH_STATE_TTL_SECONDS = 300

# Session tồn tại 7 ngày.
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60

OAUTH_STATE_PREFIX = "ita:auth:oauth:github:state:"
SESSION_PREFIX = "ita:auth:session:"


def _get_redis() -> Redis:
    """Sử dụng Redis connection của ứng dụng."""
    return get_redis_connection()


def create_oauth_state(browser_binding: str) -> str:
    """Tạo OAuth state và liên kết với trình duyệt khởi tạo đăng nhập."""
    if not browser_binding:
        raise ValueError("browser_binding không được rỗng")

    state = secrets.token_urlsafe(32)

    _get_redis().set(
        f"{OAUTH_STATE_PREFIX}{state}",
        browser_binding,
        ex=OAUTH_STATE_TTL_SECONDS,
    )

    return state


def consume_oauth_state(state: str, browser_binding: str) -> bool:
    """Tiêu thụ state một lần và xác minh trình duyệt bằng GETDEL."""
    if not state or not browser_binding:
        return False

    result = _get_redis().getdel(f"{OAUTH_STATE_PREFIX}{state}")

    if result is None:
        return False

    if isinstance(result, bytes):
        result = result.decode("utf-8")

    return secrets.compare_digest(result, browser_binding)


def create_session(user_id: int) -> str:
    """Tạo session ID ngẫu nhiên và lưu user ID vào Redis."""
    if user_id <= 0:
        raise ValueError("user_id phải lớn hơn 0")

    session_id = secrets.token_urlsafe(32)

    _get_redis().set(
        f"{SESSION_PREFIX}{session_id}",
        str(user_id),
        ex=SESSION_TTL_SECONDS,
    )

    return session_id


def get_session_user_id(session_id: str | None) -> int | None:
    """Lấy user ID từ session; trả về None nếu session không hợp lệ."""
    if not session_id:
        return None

    result = _get_redis().get(f"{SESSION_PREFIX}{session_id}")

    if result is None:
        return None

    try:
        return int(result)
    except (TypeError, ValueError):
        return None


def revoke_session(session_id: str | None) -> bool:
    """Thu hồi session bằng cách xóa key trong Redis."""
    if not session_id:
        return False

    return bool(_get_redis().delete(f"{SESSION_PREFIX}{session_id}"))


class GitHubAccountConflictError(Exception):
    """GitHub identity hoặc email đã thuộc về tài khoản khác."""


def get_or_create_github_user(
    db: Session,
    identity: GitHubIdentity,
) -> User:
    """Tìm hoặc tạo User từ danh tính GitHub đã xác minh."""

    provider = "github"

    if not identity.provider_user_id or not identity.email:
        raise ValueError("GitHub identity không hợp lệ.")

    email = identity.email.strip().lower()

    if not email:
        raise ValueError("Email GitHub không hợp lệ.")

    # 1. Tìm tài khoản OAuth đã liên kết bằng GitHub ID.
    oauth_result = db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == identity.provider_user_id,
        )
    )

    oauth_account = oauth_result.scalar_one_or_none()

    if oauth_account is not None:
        return oauth_account.user

    # 2. Không tự động liên kết nếu email đã thuộc User khác.
    user_result = db.execute(select(User).where(User.email == email))

    existing_user = user_result.scalar_one_or_none()

    if existing_user is not None:
        raise GitHubAccountConflictError("Email đã được sử dụng bởi tài khoản khác.")

    # 3. Tạo User và OAuthAccount trong cùng transaction.
    user = User(
        email=email,
        full_name=identity.full_name.strip() or email,
        hashed_password=None,
    )

    try:
        db.add(user)
        db.flush()

        oauth_account = OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_user_id=identity.provider_user_id,
        )

        db.add(oauth_account)
        db.commit()

        return user

    except IntegrityError as exc:
        db.rollback()

        # Có thể một request khác vừa tạo cùng GitHub identity.
        oauth_result = db.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == identity.provider_user_id,
            )
        )

        oauth_account = oauth_result.scalar_one_or_none()

        if oauth_account is not None:
            return oauth_account.user

        raise GitHubAccountConflictError(
            "Không thể tạo tài khoản GitHub do dữ liệu bị trùng."
        ) from exc

    except Exception:
        db.rollback()
        raise
