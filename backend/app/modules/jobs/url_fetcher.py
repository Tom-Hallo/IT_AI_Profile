"""URL fetcher an toàn chống SSRF cho JD Analysis (PBI-025).

Quy tắc bảo mật:
1. Chỉ chấp nhận giao thức http và https.
2. Phân giải hostname sang địa chỉ IP và kiểm tra nghiêm ngặt:
   - Chặn toàn bộ IP loopback (127.0.0.0/8, ::1)
   - Chặn toàn bộ IP private/nội bộ (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
   - Chặn link-local / cloud metadata (169.254.169.254, fe80::/10)
   - Chặn multicast, broadcast, reserved IP
3. Giới hạn timeout ngắn (8s) và kích thước tối đa (2MB).
4. Fallback sang text input cho người dùng khi lỗi.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
DEFAULT_TIMEOUT_SECONDS = 8.0


class URLFetchError(Exception):
    """Ngoại lệ khi không thể tải URL (mạng, timeout, 4xx/5xx)."""

    def __init__(self, message: str, fallback_suggested: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.fallback_suggested = fallback_suggested


class SSRFBlockedError(URLFetchError):
    """Ngoại lệ khi URL trỏ tới địa chỉ IP nội bộ bị cấm (SSRF Protection)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, fallback_suggested=True)


def is_safe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Kiểm tra IP có an toàn để gọi ra bên ngoài không."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False

    if isinstance(ip, ipaddress.IPv4Address):
        if str(ip).startswith("169.254."):
            return False
        cgnat = ipaddress.IPv4Network("100.64.0.0/10")
        if ip in cgnat:
            return False

    return True


def validate_url_security(url_str: str) -> str:
    """Validate scheme và hostname an toàn chống SSRF."""
    parsed = urlparse(url_str)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFBlockedError(
            f"Giao thức '{scheme}' không được hỗ trợ. Chỉ cho phép http/https."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("URL không chứa hostname hợp lệ.")

    if hostname.lower() in ("localhost", "localhost.localdomain", "broadcasthost"):
        raise SSRFBlockedError(
            "Không được phép truy cập địa chỉ máy chủ nội bộ (localhost)."
        )

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise URLFetchError(
            f"Không thể phân giải tên miền '{hostname}': {exc}"
        ) from exc

    resolved_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in addr_infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            resolved_ips.append(ip_obj)
        except ValueError:
            continue

    if not resolved_ips:
        raise URLFetchError(f"Không tìm thấy địa chỉ IP cho tên miền '{hostname}'.")

    for ip in resolved_ips:
        if not is_safe_ip(ip):
            raise SSRFBlockedError(
                f"Tên miền '{hostname}' phân giải tới IP nội bộ/không an toàn ({ip}). "
                "Yêu cầu bị chặn để bảo vệ hệ thống."
            )

    return url_str


def extract_text_from_html(html_content: str) -> str:
    """Bóc tách văn bản thô từ nội dung HTML."""
    cleaned = re.sub(r"(?is)<script.*?</script>", " ", html_content)
    cleaned = re.sub(r"(?is)<style.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?is)<!--.*?-->", " ", cleaned)
    block_tags = r"</?(p|div|br|li|h[1-6]|tr|td|section|article)[^>]*>"
    cleaned = re.sub(block_tags, "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    lines = [line.strip() for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line)


def fetch_jd_from_url(
    url_str: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Tải nội dung JD từ URL một cách an toàn và trích xuất text."""
    safe_url = validate_url_security(url_str)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 ITTalentProfileBot/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=3,
        ) as client:
            resp = client.get(safe_url, headers=headers)

            final_url = str(resp.url)
            if final_url != safe_url:
                validate_url_security(final_url)

            if resp.status_code >= 400:
                raise URLFetchError(
                    f"Máy chủ đích trả về mã lỗi HTTP {resp.status_code}. "
                    "Vui lòng thử sao chép nội dung JD và dán trực tiếp."
                )

            content_bytes = resp.content
            if len(content_bytes) > MAX_RESPONSE_BYTES:
                mb = MAX_RESPONSE_BYTES // (1024 * 1024)
                raise URLFetchError(
                    f"Trang web quá lớn (> {mb}MB). Vui lòng dán nội dung JD."
                )

            content_type = resp.headers.get("content-type", "").lower()
            text_body = resp.text

            if "html" in content_type:
                extracted = extract_text_from_html(text_body)
            else:
                extracted = text_body.strip()

            if len(extracted) < 50:
                raise URLFetchError(
                    "Không trích xuất được đủ văn bản từ trang web (yêu cầu JS/login). "
                    "Hãy copy văn bản JD dán trực tiếp."
                )

            return extracted

    except httpx.TimeoutException as exc:
        raise URLFetchError(
            "Yêu cầu tải trang bị quá thời gian. Vui lòng dán văn bản JD trực tiếp."
        ) from exc
    except (httpx.RequestError, Exception) as exc:
        raise URLFetchError(
            f"Không thể kết nối đến URL ({type(exc).__name__}). "
            "Vui lòng kiểm tra lại link hoặc dán nội dung JD."
        ) from exc
