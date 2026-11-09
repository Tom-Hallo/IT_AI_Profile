"""Đưa job vào hàng đợi và xem trạng thái job.

Dùng trong code (Backend):
    from app.workers.enqueue import enqueue_ping
    job = enqueue_ping("xin chao")
    job.id

Dùng từ dòng lệnh (chạy trong thư mục backend/):
    python -m app.workers.enqueue ping --message "xin chao" --wait 15
    python -m app.workers.enqueue status <job_id>
"""

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

from redis.exceptions import RedisError
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.core.redis import get_redis_connection
from app.workers.queues import (
    FAILURE_TTL_SECONDS,
    JOB_TIMEOUT_SECONDS,
    RESULT_TTL_SECONDS,
    SERIALIZER,
    get_queue,
)
from app.workers.tasks.ping import ping

POLL_INTERVAL_SECONDS = 0.5
FINAL_STATUSES = {"finished", "failed", "stopped", "canceled"}


def enqueue_task(
    func: Callable[..., Any] | str, *args: Any, queue_name: str | None = None
) -> Job:
    """Đưa một hàm (hoặc đường dẫn dạng chuỗi tới hàm) vào hàng đợi.

    `args` phải là kiểu JSON đơn giản. Đây là cách duy nhất nên dùng để enqueue,
    để thời hạn và serializer luôn nhất quán.
    """
    return get_queue(queue_name).enqueue(
        func,
        *args,
        job_timeout=JOB_TIMEOUT_SECONDS,
        result_ttl=RESULT_TTL_SECONDS,
        failure_ttl=FAILURE_TTL_SECONDS,
    )


def enqueue_ping(message: str = "ping", queue_name: str | None = None) -> Job:
    """Enqueue job mẫu `ping`."""
    return enqueue_task(ping, message, queue_name=queue_name)


def fetch_job(job_id: str) -> Job:
    """Lấy job theo id; ném NoSuchJobError nếu không còn (hết hạn hoặc sai id)."""
    return Job.fetch(job_id, connection=get_redis_connection(), serializer=SERIALIZER)


def describe_job(job: Job) -> dict[str, Any]:
    """Tóm tắt trạng thái job để in ra. Không chứa traceback (có thể dài, nhạy cảm)."""
    status = job.get_status(refresh=True).value
    summary: dict[str, Any] = {"job_id": job.id, "queue": job.origin, "status": status}
    if status == "finished":
        summary["result"] = job.return_value()
    return summary


def wait_for_job(job: Job, timeout_seconds: int) -> str:
    """Chờ job kết thúc hoặc hết thời gian; trả về trạng thái cuối cùng đọc được."""
    deadline = time.monotonic() + timeout_seconds
    status = job.get_status(refresh=True).value
    while status not in FINAL_STATUSES and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        status = job.get_status(refresh=True).value
    return status


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.workers.enqueue",
        description="Enqueue job và xem trạng thái job.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ping_cmd = commands.add_parser("ping", help="Enqueue job mẫu ping")
    ping_cmd.add_argument(
        "--message", default="ping", help="Chuỗi gửi kèm (mặc định: ping)"
    )
    ping_cmd.add_argument(
        "--queue", default=None, help="Tên hàng đợi (mặc định: WORKER_QUEUES[0])"
    )
    ping_cmd.add_argument(
        "--wait",
        type=int,
        default=0,
        metavar="GIAY",
        help="Chờ tối đa GIAY giây để job xong",
    )

    status_cmd = commands.add_parser("status", help="Xem trạng thái và kết quả của job")
    status_cmd.add_argument("job_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Mã thoát: 0 thành công, 1 lỗi hoặc job lỗi, 2 hết thời gian chờ."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "ping":
            job = enqueue_ping(args.message, args.queue)
            if args.wait > 0:
                wait_for_job(job, args.wait)
            summary = describe_job(job)
            print(json.dumps(summary, ensure_ascii=False))
            if args.wait > 0 and summary["status"] not in FINAL_STATUSES:
                return 2
            return 1 if summary["status"] in {"failed", "stopped", "canceled"} else 0

        job = fetch_job(args.job_id)
        print(json.dumps(describe_job(job), ensure_ascii=False))
        return 0
    except NoSuchJobError:
        print("Khong tim thay job (sai id hoac da het han).", file=sys.stderr)
        return 1
    except RedisError as exc:
        # Chỉ in tên loại lỗi: thông báo gốc có thể chứa host/URL kết nối.
        print(f"Khong ket noi duoc Redis ({type(exc).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
