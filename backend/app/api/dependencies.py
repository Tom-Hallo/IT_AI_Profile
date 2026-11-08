"""Dependencies dùng chung cho API."""

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.service import get_session_user_id
from app.modules.users.models import User

SESSION_COOKIE = "ita_session"


def get_current_user(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_session),  # noqa: B008
) -> User:
    """Lấy người dùng hiện tại từ session cookie."""

    user_id = get_session_user_id(session_id)

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bạn chưa đăng nhập hoặc phiên đăng nhập đã hết hạn.",
        )

    statement = select(User).where(User.id == user_id)
    user = db.scalar(statement)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không tồn tại hoặc phiên đăng nhập không hợp lệ.",
        )

    return user
