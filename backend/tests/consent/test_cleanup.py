"""Focused filesystem tests; no database needed."""

import uuid

from app.modules.consent import cleanup


def test_purge_job_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(cleanup, "ROOT", tmp_path)
    job_id = uuid.uuid4()
    folder = cleanup.job_directory(job_id)
    folder.mkdir()
    (folder / "source.py").write_text("secret")
    cleanup.purge_job_directory(job_id)
    assert not folder.exists()
    cleanup.purge_job_directory(job_id)  # idempotent


def test_purge_does_not_follow_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(cleanup, "ROOT", tmp_path)
    outside = tmp_path.parent / ("outside-" + uuid.uuid4().hex)
    outside.mkdir()
    try:
        (outside / "keep.txt").write_text("keep")
        link = cleanup.job_directory(uuid.uuid4())
        link.symlink_to(outside, target_is_directory=True)
        cleanup.purge_job_directory(uuid.UUID(link.name))
        assert (outside / "keep.txt").read_text() == "keep"
    finally:
        import shutil

        shutil.rmtree(outside)
