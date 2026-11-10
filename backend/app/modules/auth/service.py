"""Redis services for GitHub OAuth state and application sessions."""

import logging
import secrets
from datetime import UTC, datetime

from cryptography.fernet import InvalidToken
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.redis import get_redis_connection
from app.core.security import decrypt_token, encrypt_token
from app.modules.auth.github import GitHubIdentity
from app.modules.auth.models import OAuthAccount
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# OAuth state tồn tại 5 phút.
OAUTH_STATE_TTL_SECONDS = 300

# Session tồn tại 7 ngày.
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60

OAUTH_STATE_PREFIX = "ita:auth:oauth:github:state:"
OAUTH_ACCESS_MODE_PREFIX = "ita:auth:oauth:github:access_mode:"
SESSION_PREFIX = "ita:auth:session:"


def _get_redis() -> Redis:
    """Sử dụng Redis connection của ứng dụng."""
    return get_redis_connection()


def create_oauth_state(browser_binding: str, access_mode: str | None = None) -> str:
    """Tạo OAuth state và liên kết với trình duyệt khởi tạo đăng nhập."""
    if not browser_binding:
        raise ValueError("browser_binding không được rỗng")

    state = secrets.token_urlsafe(32)

    _get_redis().set(
        f"{OAUTH_STATE_PREFIX}{state}",
        browser_binding,
        ex=OAUTH_STATE_TTL_SECONDS,
    )

    if access_mode in ("public_only", "private_enabled"):
        _get_redis().set(
            f"{OAUTH_ACCESS_MODE_PREFIX}{state}",
            access_mode,
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


def consume_oauth_access_mode(state: str) -> str:
    """Tiêu thụ access_mode một lần từ Redis; mặc định là 'public_only'."""
    if not state:
        return "public_only"

    result = _get_redis().getdel(f"{OAUTH_ACCESS_MODE_PREFIX}{state}")
    if result is None:
        return "public_only"

    if isinstance(result, bytes):
        result = result.decode("utf-8")

    return result if result in ("public_only", "private_enabled") else "public_only"


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


def _update_github_oauth_token(
    db: Session,
    oauth_account: OAuthAccount,
    identity: GitHubIdentity,
    access_mode: str = "public_only",
) -> None:
    """
    Cập nhật GitHub OAuth token an toàn.

    - Mã hóa token trước khi lưu.
    - Cập nhật access_mode độc lập với scope GitHub.
    - Rollback nếu mã hóa hoặc commit thất bại.
    - Không bỏ qua lỗi.
    - Không đưa token thật vào thông báo lỗi.
    """

    if not identity.access_token:
        return

    try:
        encrypted_token = encrypt_token(identity.access_token)

        oauth_account.encrypted_access_token = encrypted_token
        oauth_account.scope = identity.scope
        oauth_account.access_mode = (
            access_mode
            if access_mode in ("public_only", "private_enabled")
            else "public_only"
        )
        oauth_account.token_updated_at = func.now()

        db.commit()

    except Exception:
        db.rollback()
        raise


def get_or_create_github_user(
    db: Session,
    identity: GitHubIdentity,
    access_mode: str = "public_only",
) -> User:
    """
    Tìm hoặc tạo User từ danh tính GitHub đã xác minh.

    Security:
    - Không tự động liên kết email đã thuộc tài khoản khác.
    - Mã hóa GitHub access token trước khi lưu.
    - Lưu access_mode do người dùng chọn ('public_only' hoặc 'private_enabled').
    - Không bỏ qua lỗi mã hóa hoặc database.
    - Rollback khi transaction thất bại.
    - Xử lý race condition khi tạo OAuth account.
    """

    provider = "github"

    # ========================================================
    # 1. VALIDATE GITHUB IDENTITY
    # ========================================================

    if not identity.provider_user_id or not identity.email:
        raise ValueError("GitHub identity không hợp lệ.")

    email = identity.email.strip().lower()

    if not email:
        raise ValueError("Email GitHub không hợp lệ.")

    # ========================================================
    # 2. CHECK EXISTING GITHUB OAUTH ACCOUNT
    # ========================================================

    oauth_result = db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == identity.provider_user_id,
        )
    )

    oauth_account = oauth_result.scalar_one_or_none()

    if oauth_account is not None:
        # Nếu cập nhật token thất bại, lỗi được truyền lên.
        # Không tiếp tục như thể token đã lưu thành công.
        _update_github_oauth_token(
            db=db,
            oauth_account=oauth_account,
            identity=identity,
            access_mode=access_mode,
        )

        return oauth_account.user

    # ========================================================
    # 3. CHECK EMAIL CONFLICT
    # ========================================================

    user_result = db.execute(select(User).where(User.email == email))

    existing_user = user_result.scalar_one_or_none()

    if existing_user is not None:
        raise GitHubAccountConflictError("Email đã được sử dụng bởi tài khoản khác.")

    # ========================================================
    # 4. ENCRYPT GITHUB TOKEN
    # ========================================================

    encrypted_token = None

    if identity.access_token:
        # Không dùng try/except pass.
        # Nếu mã hóa thất bại, dừng quy trình.
        encrypted_token = encrypt_token(identity.access_token)

    # ========================================================
    # 5. CREATE USER AND OAUTH ACCOUNT
    # ========================================================

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
            encrypted_access_token=encrypted_token,
            scope=identity.scope,
            access_mode=(
                access_mode
                if access_mode in ("public_only", "private_enabled")
                else "public_only"
            ),
            token_updated_at=(func.now() if encrypted_token else None),
        )

        db.add(oauth_account)
        db.commit()

        return user

    # ========================================================
    # 6. HANDLE CONCURRENT GITHUB LOGIN
    # ========================================================

    except IntegrityError as exc:
        db.rollback()

        # Có thể request khác đã tạo OAuth account
        # cho cùng GitHub identity trước đó.
        oauth_result = db.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == identity.provider_user_id,
            )
        )

        oauth_account = oauth_result.scalar_one_or_none()

        if oauth_account is not None:
            # Cập nhật token trên tài khoản vừa được tạo.
            # Không bỏ qua lỗi cập nhật.
            _update_github_oauth_token(
                db=db,
                oauth_account=oauth_account,
                identity=identity,
                access_mode=access_mode,
            )

            return oauth_account.user

        raise GitHubAccountConflictError(
            "Không thể tạo tài khoản GitHub do dữ liệu bị trùng."
        ) from exc

    # ========================================================
    # 7. HANDLE OTHER ERRORS
    # ========================================================

    except Exception:
        db.rollback()
        raise


def has_repo_scope(scope_str: str | None) -> bool:
    """Kiểm tra xem chuỗi scope trả về từ GitHub có chứa scope 'repo' hay không."""
    if not scope_str:
        return False
    scopes = {s.strip() for s in scope_str.replace(",", " ").split() if s.strip()}
    return "repo" in scopes


def has_private_access(db: Session, user_id: int) -> bool:
    """Xác thực người dùng có quyền truy cập private repository hay không.

    Fail-closed policy:
    1. OAuthAccount tồn tại với provider='github'.
    2. Token mã hóa tồn tại (người dùng đang liên kết GitHub).
    3. Ứng dụng được cấp quyền truy cập private (access_mode == 'private_enabled').
    4. Token thực tế từ GitHub có chứa scope 'repo'.
    """
    stmt = select(OAuthAccount).where(
        OAuthAccount.user_id == user_id,
        OAuthAccount.provider == "github",
    )
    account = db.scalar(stmt)
    if (
        not account
        or not hasattr(account, "encrypted_access_token")
        or not account.encrypted_access_token
    ):
        return False
    if getattr(account, "access_mode", "public_only") != "private_enabled":
        return False
    return has_repo_scope(getattr(account, "scope", None))


def get_user_github_token(
    db: Session,
    user_id: int,
) -> tuple[str | None, str | None]:
    """Lấy và giải mã GitHub access token cùng scope đã cấp của user."""
    stmt = select(OAuthAccount).where(
        OAuthAccount.user_id == user_id,
        OAuthAccount.provider == "github",
    )
    account = db.scalar(stmt)
    encrypted = getattr(account, "encrypted_access_token", None)
    if not account or not encrypted:
        return None, None

    try:
        token = decrypt_token(encrypted)
        return token, getattr(account, "scope", None)
    except (InvalidToken, ValueError, TypeError):
        return None, None


def disconnect_github(db: Session, user_id: int) -> bool:
    """Xóa token, hủy liên kết GitHub, reset access_mode và thu hồi quyền riêng tư."""
    stmt = select(OAuthAccount).where(
        OAuthAccount.user_id == user_id,
        OAuthAccount.provider == "github",
    )
    account = db.scalar(stmt)
    if not account:
        return False

    now_utc = datetime.now(UTC)
    try:
        account.encrypted_access_token = None
        account.scope = None
        account.token_updated_at = None
        account.access_mode = "public_only"

        # 1. Thu hồi các bản ghi PrivateConsent đang hoạt động của người dùng
        from app.modules.consent.models import PrivateConsent

        consents = db.scalars(
            select(PrivateConsent)
            .where(
                PrivateConsent.user_id == user_id,
                PrivateConsent.revoked_at.is_(None),
            )
            .with_for_update()
        ).all()
        for c in consents:
            c.granted = False
            c.revoked_at = now_utc

        # 2. Yêu cầu hủy các tiến trình phân tích repo riêng tư đang hoạt động
        from app.modules.analysis.models import ACTIVE, AnalysisJob
        from app.modules.github.models import Repository

        active_jobs = db.scalars(
            select(AnalysisJob)
            .join(Repository, AnalysisJob.repo_id == Repository.id)
            .where(
                AnalysisJob.user_id == user_id,
                AnalysisJob.status.in_(ACTIVE),
                Repository.private.is_(True),
            )
            .with_for_update()
        ).all()
        for aj in active_jobs:
            aj.status = "cancel_requested"

        # Thực hiện commit nguyên tử cho tất cả thay đổi trên cơ sở dữ liệu
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(
            "Lỗi giao dịch khi ngắt kết nối GitHub cho user %s: %s",
            user_id,
            exc,
            exc_info=True,
        )
        raise

    # 3. Xóa cache trạng thái sync trên Redis (best-effort)
    try:
        redis = _get_redis()
        redis.delete(f"ita:github:sync:{user_id}")
    except Exception as exc:
        logger.warning("Lỗi xóa cache sync khi ngắt kết nối GitHub: %s", exc)

    # 4. Xóa in-memory analysis cache cho các repo của user (best-effort)
    try:
        from app.modules.analysis.service import clear_user_analysis_cache

        clear_user_analysis_cache(db, user_id)
    except Exception as exc:
        logger.warning("Lỗi xóa analysis cache khi ngắt kết nối GitHub: %s", exc)

    return True
