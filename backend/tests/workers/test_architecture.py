"""Các quy tắc kiến trúc của Worker (Task 06), có test canh giữ như phía Database."""

import re
from pathlib import Path

WORKERS_DIR = Path(__file__).resolve().parents[2] / "app" / "workers"


def _sources() -> dict[str, str]:
    return {
        str(path.relative_to(WORKERS_DIR)): path.read_text(encoding="utf-8")
        for path in WORKERS_DIR.rglob("*.py")
    }


def _offenders(pattern: str) -> list[str]:
    return [name for name, text in _sources().items() if re.search(pattern, text)]


def test_workers_do_not_read_environment_directly():
    # Chỉ app/core/config.py được đọc biến môi trường.
    assert _offenders(r"os\.environ|os\.getenv|\bgetenv\(") == []


def test_workers_do_not_create_their_own_redis_or_db_clients():
    assert _offenders(r"Redis\.from_url|Redis\(|\bcreate_engine\(") == []


def test_worker_process_does_not_touch_the_database():
    # Tiến trình worker cha không được truy cập DB (rủi ro fork, HANDOFF Database mục
    # B).
    # Job cần DB tự import session_scope BÊN TRONG hàm job (thư mục tasks/).
    for name in ("worker.py", "queues.py", "enqueue.py"):
        assert "app.db" not in _sources()[name], name


def test_workers_never_use_pickle_serializer():
    assert _offenders(r"PickleSerializer|import pickle|['\"]pickle['\"]") == []
