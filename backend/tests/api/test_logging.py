import logging

from app.core.logging import REDACTED, RedactingFilter, redact


def test_redacts_credentials_in_urls():
    text = (
        "connect postgresql+psycopg://ita:Hunter2@postgres:5432/db "
        "and redis://:pw123@redis:6379/0"
    )
    out = redact(text)
    assert "Hunter2" not in out
    assert "pw123" not in out
    assert f"postgresql+psycopg://{REDACTED}@postgres:5432/db" in out


def test_redacts_key_value_secrets():
    out = redact("password=abc123 token: xyz789 api_key=K-1")
    for secret in ("abc123", "xyz789", "K-1"):
        assert secret not in out


def test_filter_redacts_formatted_message():
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "url %s", ("postgresql://u:pw@h/d",), None
    )
    assert RedactingFilter().filter(record)
    assert "pw@" not in record.getMessage()


def test_normal_message_unchanged():
    assert redact("backend 0.1.0 khởi động") == "backend 0.1.0 khởi động"
