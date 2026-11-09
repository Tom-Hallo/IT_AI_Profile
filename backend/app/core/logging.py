"""Logging an toàn (Blueprint S7): không để lộ secret hay URL kết nối trong log."""

import logging
import re

# user:password@ trong URL kết nối (postgresql+psycopg://u:p@host, redis://:p@host ...)
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)[^\s/@]*@")
# password=..., token=..., secret=..., api_key=... dạng key=value hoặc key: value
_KEY_VALUE = re.compile(
    r"(?i)(?P<key>password|passwd|pwd|secret|token|api[_-]?key|authorization)"
    r"(?P<sep>\s*[=:]\s*)(?P<val>[^\s,;&'\"]+)"
)

REDACTED = "***"


def redact(text: str) -> str:
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group('scheme')}{REDACTED}@", text)
    return _KEY_VALUE.sub(lambda m: f"{m.group('key')}{m.group('sep')}{REDACTED}", text)


class RedactingFilter(logging.Filter):
    """Che thông tin nhạy cảm trong thông điệp (đã định dạng) trước khi ghi ra."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def configure_logging(level: str) -> None:
    """Cấu hình root logger; gọi một lần khi khởi động app."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
