"""Job mẫu: chứng minh hàng đợi hoạt động. Không dùng DB, không gọi dịch vụ ngoài."""

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def ping(message: str = "ping") -> dict[str, object]:
    """Trả về một dict nhỏ cho biết worker đã nhận và chạy job."""
    # Cố ý không log `message` (dữ liệu do người gọi cung cấp).
    logger.info("Job ping da duoc thuc thi")
    return {
        "pong": True,
        "message": message,
        "finished_at": datetime.now(UTC).isoformat(),
    }
