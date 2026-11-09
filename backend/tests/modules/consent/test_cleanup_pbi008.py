from uuid import uuid4
from app.modules.consent.cleanup import cleanup_job_directory


def test_cleanup_removes_source_and_parse_cache(tmp_path):
    job_id = uuid4()
    source = tmp_path / str(job_id) / "clone"
    cache = tmp_path / str(job_id) / "parse_cache"
    source.mkdir(parents=True)
    cache.mkdir()
    (source / "private.py").write_text("SECRET_SOURCE", encoding="utf-8")
    (cache / "ast.json").write_text("PRIVATE_CACHE", encoding="utf-8")
    assert cleanup_job_directory(tmp_path, job_id)
    assert not (tmp_path / str(job_id)).exists()
    assert not cleanup_job_directory(tmp_path, job_id)


def test_cleanup_preserves_other_jobs(tmp_path):
    first, second = uuid4(), uuid4()
    (tmp_path / str(first)).mkdir()
    (tmp_path / str(second)).mkdir()
    cleanup_job_directory(tmp_path, first)
    assert (tmp_path / str(second)).exists()
