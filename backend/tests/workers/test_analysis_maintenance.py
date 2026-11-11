from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.workers import maintenance


def test_recovery_enqueues_orphan_and_cleans_interrupted_work(monkeypatch):
    db = MagicMock()
    orphan = SimpleNamespace(id=uuid4(), status="queued", execution_token=None)
    abandoned = SimpleNamespace(
        id=uuid4(), status="running", execution_token=uuid4(), progress=35
    )
    db.scalars.return_value.all.return_value = [orphan, abandoned]
    enqueue = MagicMock()
    enqueue.return_value.get_status.return_value = "queued"
    cleanup = MagicMock()
    monkeypatch.setattr(maintenance, "session_scope", lambda: nullcontext(db))
    monkeypatch.setattr(maintenance, "enqueue_task", enqueue)
    monkeypatch.setattr(maintenance, "request_cleanup", cleanup)

    maintenance.recover_analysis_jobs()

    enqueue.assert_called_once_with(
        "app.workers.tasks.analysis.run_analysis",
        str(orphan.id),
        job_id=f"analysis-{orphan.id}",
    )
    assert orphan.status == "queued"
    assert abandoned.status == "failed"
    assert abandoned.error_code == "WORKER_INTERRUPTED"
    cleanup.assert_called_once_with(db, abandoned, reason="worker_interrupted")
