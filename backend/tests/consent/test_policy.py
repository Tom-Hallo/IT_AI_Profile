from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.modules.consent import service


@pytest.mark.parametrize(
    "paths",
    [
        [],
        ["../secret"],
        [".env"],
        ["src/../secret.py"],
        ["/etc/passwd"],
        ["src\\a.py"],
        ["src/*.py"],
        ["a.py", "a.py"],
    ],
)
def test_unsafe_scope_rejected(paths):
    with pytest.raises(HTTPException) as exc:
        service.validate_paths(paths)
    assert exc.value.status_code == 422


def test_missing_consent_denied(monkeypatch):
    repo = Mock(private=True)
    monkeypatch.setattr(service, "owned_repo", lambda *_: repo)
    db = Mock()
    db.scalar.return_value = None
    with pytest.raises(HTTPException) as exc:
        service.require_double_consent(db, 1, 10, "openai", ["src/main.py"])
    assert exc.value.status_code == 403


def test_provider_mismatch_denied():
    with pytest.raises(HTTPException) as exc:
        service.normalize_type("external_ai", "unknown")
    assert exc.value.status_code == 422
