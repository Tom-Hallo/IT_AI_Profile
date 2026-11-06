"""Test đơn vị cho Worker: KHÔNG cần Redis hay DB (Redis.from_url chỉ tạo client, chưa kết nối)."""

import json
import logging
import os
from types import SimpleNamespace

import pytest
from rq import Worker
from rq.worker import SimpleWorker

from app.workers import queues
from app.workers import worker as worker_module
from app.workers.tasks.ping import ping


def test_ping_returns_json_serializable_pong():
    result = ping("xin chao")
    assert result["pong"] is True
    assert result["message"] == "xin chao"
    json.dumps(result)  # job chỉ được trả về kiểu JSON


def test_queue_uses_json_serializer_and_first_configured_name():
    queue = queues.get_queue()
    assert queue.name == queues.default_queue_name() == "default"
    assert queue.serializer.__name__ == "JSONSerializer"
    assert queues.get_queue("khac").name == "khac"


def test_worker_class_is_fork_based_on_posix(monkeypatch):
    monkeypatch.setattr(worker_module, "_is_windows", lambda: False)
    assert worker_module.get_worker_class() is Worker


def test_worker_class_avoids_fork_and_spawn_on_windows(monkeypatch):
    monkeypatch.setattr(worker_module, "_is_windows", lambda: True)
    assert worker_module.get_worker_class() is SimpleWorker


@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="RQ Worker gọi CLIENT SETNAME khi khởi tạo nên cần Redis đang chạy",
)
def test_build_worker_listens_to_configured_queues_with_json_serializer():
    worker = worker_module.build_worker(["a", "b"])
    assert [q.name for q in worker.queues] == ["a", "b"]
    assert worker.serializer.__name__ == "JSONSerializer"


def test_main_exits_with_error_when_redis_is_unreachable(monkeypatch, caplog):
    def boom() -> None:
        raise ConnectionError("redis://:s3cret-pass@host:6379/0 refused")

    monkeypatch.setattr(worker_module, "check_redis", boom)
    # configure_logging thay handler của root logger; giữ lại để caplog còn nhận log.
    monkeypatch.setattr(worker_module, "configure_logging", lambda level: None)
    with caplog.at_level(logging.ERROR):
        assert worker_module.main(["--burst"]) == 1
    assert "ConnectionError" in caplog.text
    assert "s3cret-pass" not in caplog.text


def test_failure_handler_logs_type_only_and_lets_rq_continue(caplog):
    job = SimpleNamespace(id="job-1", func_name="app.workers.tasks.x")
    with caplog.at_level(logging.ERROR):
        keep_going = worker_module.log_job_failure(
            job, ValueError, ValueError("token=abc123 khong duoc lo"), None
        )
    assert keep_going is True
    assert "job-1" in caplog.text and "ValueError" in caplog.text
    assert "abc123" not in caplog.text
