"""Môi trường chạy Alembic (Database Engineer, D1).

- URL kết nối KHÔNG đọc từ alembic.ini hay `os.environ`: lấy từ `app.core.config.settings`
  thông qua `app.db.session.engine`, cùng engine mà Backend và Worker dùng
  (Blueprint 1.4 và 9.3). Nhờ vậy ba bên không thể cấu hình kết nối mâu thuẫn nhau.
- Không in URL/mật khẩu ra màn hình hay log.

Khi bắt đầu có model nghiệp vụ (PBI sau): model phải được import trước khi Alembic đọc
`Base.metadata`, nếu không `--autogenerate` sẽ không thấy bảng nào. Cách làm gợi ý: tạo một
file import tất cả `app/modules/*/models.py` rồi import file đó ở vị trí đánh dấu bên dưới.
"""

from logging.config import fileConfig

from alembic import context

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: không tắt logger của ứng dụng nếu env.py bị nạp
    # trong cùng tiến trình.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# --- Vị trí import model nghiệp vụ trong tương lai (hiện CHƯA có model nào, PBI-001) ---

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Chế độ offline (`alembic upgrade head --sql`): chỉ sinh SQL, không kết nối DB."""
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Chế độ online: dùng engine chung của ứng dụng."""
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        # Tiến trình Alembic ngắn hạn: trả hết kết nối về DB khi xong.
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
