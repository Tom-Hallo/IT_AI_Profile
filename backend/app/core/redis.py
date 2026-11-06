"""Kết nối Redis dùng chung cho Backend và Worker (Blueprint mục 1.4)."""

from redis import Redis

from app.core.config import settings

CHECK_TIMEOUT_SECONDS = 3


def get_redis_connection() -> Redis:
    """Trả về kết nối Redis.

    KHÔNG bật `decode_responses`: RQ lưu dữ liệu dạng bytes và sẽ lỗi nếu bị giải mã sẵn.
    """
    return Redis.from_url(settings.redis_url.get_secret_value())


def check_redis() -> None:
    """PING Redis; quá 3 giây hoặc lỗi thì ném exception."""
    client = Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=CHECK_TIMEOUT_SECONDS,
        socket_timeout=CHECK_TIMEOUT_SECONDS,
    )
    try:
        client.ping()
    finally:
        client.close()
