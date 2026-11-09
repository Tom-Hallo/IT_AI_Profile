"""Engine và session PostgreSQL (Blueprint mục 1.4).

Chủ sở hữu: Database Engineer (D1). Backend đã viết bản đầu (tạm); các tên `engine`,
`SessionLocal`, `get_session`, `check_database` và hành vi của chúng được GIỮ NGUYÊN.

Nguyên tắc "một nguồn cấu hình":
- URL kết nối chỉ lấy từ `settings.database_url` (app/core/config.py).
- Đây là NƠI DUY NHẤT gọi `create_engine`. Backend (API), Worker và Alembic
(migrations/env.py)
  đều import `engine` từ đây, nên không thể có hai cấu hình kết nối mâu thuẫn nhau.
  Module nghiệp vụ KHÔNG được tự tạo engine (có test kiểm tra quy tắc này).
- Không bao giờ log URL kết nối (chứa mật khẩu).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

CHECK_TIMEOUT_SECONDS = 3

# create_engine không mở kết nối ngay, nên import module này không cần DB đang chạy.
engine = create_engine(
    settings.database_url.get_secret_value(),
    # Kiểm tra kết nối còn sống trước khi dùng: DB restart không làm API/worker lỗi dai
    # dẳng.
    pool_pre_ping=True,
    connect_args={"connect_timeout": CHECK_TIMEOUT_SECONDS},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Dependency của FastAPI: mỗi request một session, luôn đóng khi xong.

    Không tự commit: code gọi chủ động `session.commit()`. Nếu có lỗi hoặc quên commit,
    thay đổi bị hủy khi session đóng.
    """
    with SessionLocal() as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Dành cho Worker và script (ngoài FastAPI):
    một đơn vị công việc = một transaction.

    Thành công thì commit, có lỗi thì rollback rồi ném lại lỗi, cuối cùng luôn đóng
    session.
    Quy ước Blueprint 9.4: mỗi task của worker tự mở session riêng bằng hàm này.
    """
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def check_database() -> None:
    """Chạy `SELECT 1`; lỗi hoặc quá 3 giây thì ném exception."""
    with engine.connect() as connection:
        connection.execute(text("SET LOCAL statement_timeout = 3000"))
        connection.execute(text("SELECT 1"))
