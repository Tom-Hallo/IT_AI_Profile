from types import SimpleNamespace

from app.modules.profile_sharing.service import (
    ALLOWED_FIELDS,
    new_token,
    public_payload,
    token_digest,
)


def test_token_is_random_and_hashed():
    first, second = new_token(), new_token()
    assert first != second
    assert len(first) >= 40
    assert len(token_digest(first)) == 64
    assert first not in token_digest(first)


def test_allowlist_excludes_sensitive_fields():
    assert "cv" not in ALLOWED_FIELDS
    assert "access_token" not in ALLOWED_FIELDS
    assert "evidence" not in ALLOWED_FIELDS
    assert "private_repositories" not in ALLOWED_FIELDS
    user = SimpleNamespace(
        full_name="Public Name", email="secret@example.com", hashed_password="SECRET"
    )
    assert public_payload(None, user, {"full_name", "email", "access_token"}) == {
        "full_name": "Public Name"
    }
