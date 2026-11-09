"""Kiểm thử tích hợp với Redis THẬT: enqueue -> Redis lưu job -> worker nhận -> job chạy xong.

Mặc định bị bỏ qua. Chạy: RUN_INTEGRATION=1 pytest tests/workers
(REDIS_URL phải trỏ tới Redis đang chạy). Mỗi test dùng hàng đợi riêng và tự dọn.
"""

import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from rq import SimpleWorker
from rq.job import Job
from rq.registry import FailedJobRegistry, FinishedJobRegistry

from app.core.redis import get_redis_connection
from app.workers import enqueue as enqueue_module
from app.workers.queues import SERIALIZER, get_queue

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="cần RUN_INTEGRATION=1 và Redis đang chạy",
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture
def queue_name() -> Iterator[str]:
    name = f"ita-test-{uuid.uuid4().hex[:8]}"
    yield name
    queue = get_queue(name)
    registries = (FinishedJobRegistry(queue=queue), FailedJobRegistry(queue=queue))
    job_ids = [*queue.job_ids] + [
        job_id for reg in registries for job_id in reg.get_job_ids()
    ]
    for job_id in job_ids:
        Job.fetch(job_id, connection=queue.connection, serializer=SERIALIZER).delete()
    for registry in registries:
        queue.connection.delete(registry.key)
    queue.delete(delete_jobs=True)


def run_worker_process(queue_name: str) -> subprocess.CompletedProcess[str]:
    """Chạy đúng lệnh `python -m app.workers.worker --burst` như người dùng/DevOps."""
    env = {**os.environ, "WORKER_QUEUES": queue_name}
    return subprocess.run(
        [sys.executable, "-m", "app.workers.worker", "--burst"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_enqueue_stores_job_in_redis_as_queued(queue_name):
    job = enqueue_module.enqueue_ping("hello", queue_name)

    stored = enqueue_module.fetch_job(job.id)  # đọc lại từ Redis
    assert stored.get_status(refresh=True).value == "queued"
    assert get_queue(queue_name).count == 1


def test_worker_process_executes_job_successfully(queue_name):
    job = enqueue_module.enqueue_ping("hello", queue_name)

    completed = run_worker_process(queue_name)

    assert completed.returncode == 0, completed.stderr
    done = enqueue_module.fetch_job(job.id)
    assert done.get_status(refresh=True).value == "finished"
    result = done.return_value()
    assert result["pong"] is True and result["message"] == "hello"
    assert get_queue(queue_name).count == 0


def test_failing_job_goes_to_failed_registry_and_worker_survives(queue_name):
    # operator.truediv(1, 0) -> ZeroDivisionError, không cần định nghĩa hàm lỗi trong app/.
    job = enqueue_module.enqueue_task("operator.truediv", 1, 0, queue_name=queue_name)

    completed = run_worker_process(queue_name)

    assert completed.returncode == 0, completed.stderr
    assert enqueue_module.fetch_job(job.id).get_status(refresh=True).value == "failed"
    assert job.id in FailedJobRegistry(queue=get_queue(queue_name)).get_job_ids()
    assert "ZeroDivisionError" in completed.stderr


def test_worker_logs_never_contain_redis_password(queue_name):
    enqueue_module.enqueue_ping("hello", queue_name)
    completed = run_worker_process(queue_name)
    password = get_redis_connection().connection_pool.connection_kwargs.get("password")
    if password:
        assert password not in completed.stdout + completed.stderr


def test_cli_enqueue_wait_and_status(queue_name):
    env = {**os.environ, "WORKER_QUEUES": queue_name}
    cli = [sys.executable, "-m", "app.workers.enqueue"]

    enqueued = subprocess.run(
        [*cli, "ping", "--message", "cli", "--queue", queue_name],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=30,
    )  # fmt: skip
    assert enqueued.returncode == 0, enqueued.stderr
    job_id = json.loads(enqueued.stdout)["job_id"]
    assert json.loads(enqueued.stdout)["status"] == "queued"

    assert run_worker_process(queue_name).returncode == 0

    status = subprocess.run(
        [*cli, "status", job_id],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=30,
    )  # fmt: skip
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["result"]["message"] == "cli"


def test_in_process_simple_worker_also_works(queue_name):
    # Cùng nguyên lý nhưng không tạo tiến trình con: dễ gỡ lỗi khi test hỏng.
    job = enqueue_module.enqueue_ping("inproc", queue_name)
    queue = get_queue(queue_name)
    SimpleWorker([queue], connection=queue.connection, serializer=SERIALIZER).work(
        burst=True
    )
    assert enqueue_module.fetch_job(job.id).get_status(refresh=True).value == "finished"
