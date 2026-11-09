"""Cấu hình hàng đợi RQ dùng chung cho Backend (enqueue) và Worker (thực thi).

Quy tắc (Blueprint mục 1.4 và 9.4):
- Kết nối Redis chỉ lấy từ `app.core.redis.get_redis_connection()` (một nguồn duy nhất).
- Tên hàng đợi lấy từ `settings.worker_queues`; không đọc biến môi trường ở đây.
- Serializer là JSON ở CẢ hai phía: tham số job chỉ gồm kiểu JSON đơn giản (id, chuỗi, số),
  không dùng pickle. Bên enqueue và worker lệch serializer thì job không đọc được.
"""

from rq import Queue

from app.core.config import settings
from app.core.redis import get_redis_connection

# Tên alias serializer của RQ ("json"): dùng cùng một giá trị cho Queue và Worker.
SERIALIZER = "json"

# Thời gian tối đa một job được chạy trước khi RQ hủy nó (giây).
JOB_TIMEOUT_SECONDS = 300
# Kết quả job thành công được giữ trong Redis bao lâu (giây).
RESULT_TTL_SECONDS = 3600
# Job lỗi (kèm traceback) được giữ bao lâu để điều tra (giây).
FAILURE_TTL_SECONDS = 86400


def default_queue_name() -> str:
    """Hàng đợi mặc định khi enqueue: phần tử đầu của WORKER_QUEUES."""
    return settings.worker_queues[0]


def get_queue(name: str | None = None) -> Queue:
    """Trả về hàng đợi RQ đã gắn kết nối Redis và serializer JSON."""
    return Queue(
        name or default_queue_name(),
        connection=get_redis_connection(),
        serializer=SERIALIZER,
        default_timeout=JOB_TIMEOUT_SECONDS,
    )
