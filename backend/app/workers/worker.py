"""Tiến trình worker RQ.

Chạy (trong thư mục backend/):
    python -m app.workers.worker            # chạy liên tục
    python -m app.workers.worker --burst    # xử lý hết job đang chờ rồi thoát (dùng khi
    test)

Quy tắc:
- Cấu hình (Redis URL, tên hàng đợi, mức log) chỉ lấy từ `app.core.config.settings`.
- Tiến trình worker cha KHÔNG truy cập DB (rủi ro fork). RQ chạy mỗi job trong tiến
trình con;
  job cần DB tự mở session bằng `session_scope()` bên trong hàm job. Ngoại lệ: trên
  Windows gốc
  dùng SimpleWorker nên job chạy ngay trong tiến trình worker (chỉ để phát triển).
- Log đi qua `configure_logging` (có RedactingFilter), nên không lộ mật khẩu trong URL.
"""

import argparse
import logging
import os
from collections.abc import Sequence
from types import TracebackType

from redis.exceptions import RedisError
from rq import Queue, Worker
from rq.job import Job
from rq.worker import SimpleWorker

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.redis import check_redis, get_redis_connection
from app.workers.queues import SERIALIZER

logger = logging.getLogger(__name__)


def _is_windows() -> bool:
    return os.name == "nt"


def get_worker_class() -> type[Worker] | type[SimpleWorker]:
    """Chọn lớp worker theo hệ điều hành.

    - Docker/Linux/macOS: `Worker` mặc định của RQ, mỗi job chạy trong tiến trình con
    (fork).
    - Windows gốc: os.fork() không tồn tại, và tiến trình con của `SpawnWorker` còn gọi
      os.setpgrp() (chỉ có trên POSIX) nên không dùng được. Dùng `SimpleWorker`: chạy
      job
      ngay trong tiến trình worker, chỉ phù hợp để phát triển. Môi trường chuẩn là
      Docker.
    """
    return SimpleWorker if _is_windows() else Worker


def log_job_failure(
    job: Job,
    exc_type: type[BaseException],
    exc_value: BaseException,
    traceback: TracebackType | None,
) -> bool:
    """Ghi log gọn khi job lỗi: chỉ id, tên hàm và LOẠI lỗi.

    Không log nội dung exception hay traceback vì có thể chứa dữ liệu nhạy cảm
    (RedactingFilter chỉ che thông điệp, không che traceback).
    RQ vẫn tự chuyển job vào FailedJobRegistry; trả về True để RQ chạy tiếp các bước còn
    lại.
    """
    logger.error("Job %s (%s) loi: %s", job.id, job.func_name, exc_type.__name__)
    return True


def build_worker(queue_names: Sequence[str] | None = None) -> Worker:
    """Tạo worker gắn vào các hàng đợi (mặc định lấy từ settings.worker_queues)."""
    connection = get_redis_connection()
    queues = [
        Queue(name, connection=connection, serializer=SERIALIZER)
        for name in (queue_names or settings.worker_queues)
    ]
    worker = get_worker_class()(queues, connection=connection, serializer=SERIALIZER)
    worker.push_exc_handler(log_job_failure)
    return worker


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.workers.worker", description=__doc__
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Xử lý hết job đang chờ rồi thoát (dùng khi test)",
    )
    args = parser.parse_args(argv)

    configure_logging(settings.log_level)

    try:
        check_redis()
    except (RedisError, OSError, ValueError) as exc:
        # Chỉ ghi loại lỗi: thông báo gốc có thể chứa host/URL kết nối.
        logger.error("Khong ket noi duoc Redis (%s). Worker dung.", type(exc).__name__)
        return 1

    worker = build_worker()
    logger.info(
        "%s bat dau, hang doi: %s, che do: %s",
        type(worker).__name__,
        ",".join(settings.worker_queues),
        "burst" if args.burst else "lien tuc",
    )
    worker.work(burst=args.burst, logging_level=settings.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
