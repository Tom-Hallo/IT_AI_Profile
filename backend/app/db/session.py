"""Engine và session PostgreSQL (Blueprint mục 1.4).

LƯU Ý BÀN GIAO: viết TẠM bởi Backend đúng hợp đồng 1.4 để health check chạy được.
Chủ sở hữu thật là Database Engineer (D1): có thể thay thế/mở rộng, giữ nguyên các tên
`engine`, `get_session`, `check_database` và hành vi mô tả bên dưới.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

CHECK_TIMEOUT_SECONDS = 3

# create_engine không mở kết nối ngay, nên import module này không cần DB đang chạy.
engine = create_engine(
    settings.database_url.get_secret_value(),
    pool_pre_ping=True,
    connect_args={"connect_timeout": CHECK_TIMEOUT_SECONDS},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Dependency của FastAPI: mỗi request một session, luôn đóng khi xong."""
    with SessionLocal() as session:
        yield session


def check_database() -> None:
    """Chạy `SELECT 1`; lỗi hoặc quá 3 giây thì ném exception."""
    with engine.connect() as connection:
        connection.execute(text("SET LOCAL statement_timeout = 3000"))
        connection.execute(text("SELECT 1"))
