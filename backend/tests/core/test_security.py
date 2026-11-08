"""Tests for security token encryption and masking."""

import pytest

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.core.security import decrypt_token, encrypt_token, mask_token


def test_encrypt_and_decrypt_token_success():
    plain = "gho_1234567890abcdefghijklmnopqrstuvwxyz"
    encrypted = encrypt_token(plain)
    assert encrypted != plain
    decrypted = decrypt_token(encrypted)
    assert decrypted == plain


def test_encrypt_invalid_token_raises_error():
    with pytest.raises(ValueError, match="Token không hợp lệ"):
        encrypt_token("")


def test_decrypt_invalid_token_raises_error():
    with pytest.raises(ValueError):
        decrypt_token("not-a-valid-fernet-token")


def test_encrypt_without_key_raises_configuration_error(monkeypatch):
    from app.core import security

    fake_settings = Settings.model_construct(
        app_env="test",
        database_url=None,
        redis_url=None,
        github_token_encryption_key=None,
    )
    monkeypatch.setattr(security, "settings", fake_settings)

    with pytest.raises(ConfigurationError, match="Chưa cấu hình GITHUB_TOKEN_ENCRYPTION_KEY"):
        encrypt_token("gho_secret_token")


def test_mask_token():
    assert mask_token(None) == "(none)"
    assert mask_token("") == "(none)"
    assert mask_token("short") == "***"
    assert mask_token("gho_1234567890abcdef") == "gho_...cdef"
