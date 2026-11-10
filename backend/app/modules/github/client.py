"""GitHub REST API client với phân trang, xử lý rate limit và retry (PBI-009).

Quy tắc bảo mật:
- Token không bao giờ được log hoặc đưa vào exception message.
- Bounded retries: chỉ retry lỗi mạng và 5xx; không retry vô hạn hoặc retry lỗi 401/403.
- Rate limit 403/429 được bóc tách header X-RateLimit-Reset và Retry-After để báo chính
xác.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
import re
from datetime import datetime
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote, urlsplit

import httpx

from app.modules.analysis.evidence import UTC

logger = logging.getLogger(__name__)

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0


class GitHubApiError(Exception):
    """Lỗi an toàn khi giao tiếp với GitHub API (không chứa secret)."""


class GitHubTokenRevokedError(GitHubApiError):
    """GitHub token không hợp lệ hoặc đã bị thu hồi (HTTP 401)."""


class GitHubPermissionError(GitHubApiError):
    """Không có quyền truy cập tài nguyên (HTTP 403 Forbidden)."""


class GitHubRateLimitError(GitHubApiError):
    """Vượt quá giới hạn rate limit của GitHub (HTTP 403 Rate Limit hoặc HTTP 429)."""

    def __init__(
        self,
        message: str = "GitHub API rate limit exceeded.",
        reset_at: datetime | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reset_at = reset_at
        self.retry_after = retry_after


class GitHubNotFoundError(GitHubApiError):
    """Không tìm thấy tài nguyên trên GitHub (HTTP 404)."""


class GitHubEmptyRepositoryError(GitHubApiError):
    """Repository rỗng, chưa có commit nào (HTTP 409 Git Repository is empty)."""


class GitHubServerError(GitHubApiError):
    """Lỗi máy chủ từ phía GitHub (HTTP 5xx)."""


class GitHubNetworkError(GitHubApiError):
    """Lỗi mạng hoặc hết thời gian kết nối tới GitHub."""


def _parse_next_link(link_header: str | None) -> str | None:
    """Trích xuất URL của trang tiếp theo từ GitHub Link header.

    Ví dụ: `<https://api.github.com/user/repos?page=2>; rel="next", <...>; rel="last"`
    """
    if not link_header:
        return None
    for part in link_header.split(","):
        match = re.match(r'<([^>]+)>;\s*rel="([^"]+)"', part.strip())
        if match and match.group(2) == "next":
            return match.group(1)
    return None


class GitHubApiClient:
    """Client giao tiếp với GitHub REST API."""

    def __init__(
        self,
        access_token: str,
        base_url: str = GITHUB_API_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not access_token or not isinstance(access_token, str):
            raise ValueError("access_token không được để trống.")
        self._access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._client = client
        self._owned_client: httpx.AsyncClient | None = None
        self._context_depth: int = 0

    async def __aenter__(self) -> Self:
        self._context_depth += 1
        if self._client is None and self._owned_client is None:
            self._owned_client = httpx.AsyncClient(timeout=self.timeout)
            self._client = self._owned_client
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._context_depth = max(0, self._context_depth - 1)
        if self._context_depth == 0 and self._owned_client is not None:
            await self._owned_client.aclose()
            self._client = None
            self._owned_client = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "IT-Talent-AI-Profile",
        }

    async def _request(
        self,
        method: str,
        url_or_endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Gửi HTTP request với bounded retry và backoff có jitter cho lỗi tạm thời."""

        url = (
            url_or_endpoint
            if url_or_endpoint.startswith(("http://", "https://"))
            else f"{self.base_url}{url_or_endpoint}"
        )

        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.github.com"
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise GitHubApiError("URL GitHub API không hợp lệ.")

        async def _execute(http_client: httpx.AsyncClient) -> httpx.Response:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await http_client.request(
                        method,
                        url,
                        headers=self._headers,
                        params=params,
                    )

                    # 1. 2xx Thành công
                    if response.status_code in (200, 201, 204):
                        return response

                    # 2. 401 Unauthorized (Lỗi token cố định, không retry)
                    if response.status_code == 401:
                        raise GitHubTokenRevokedError(
                            "GitHub access token không hợp lệ hoặc đã bị thu hồi."
                        )

                    # 3. 403 Forbidden hoặc Rate Limit
                    if response.status_code == 403:
                        remaining = response.headers.get("x-ratelimit-remaining")
                        is_rate_limit = (
                            remaining == "0"
                            or "rate limit" in response.text.lower()
                            or "secondary rate limit" in response.text.lower()
                        )
                        if is_rate_limit:
                            reset_timestamp = response.headers.get("x-ratelimit-reset")
                            reset_at = None
                            if reset_timestamp:
                                try:
                                    reset_at = datetime.fromtimestamp(
                                        int(reset_timestamp), tz=UTC
                                    )
                                except (ValueError, TypeError):
                                    pass
                            retry_after_str = response.headers.get("retry-after")
                            retry_after = (
                                int(retry_after_str) if retry_after_str else None
                            )
                            raise GitHubRateLimitError(
                                "GitHub API đã đạt giới hạn yêu cầu (rate limit).",
                                reset_at=reset_at,
                                retry_after=retry_after,
                            )
                        raise GitHubPermissionError(
                            "Không có quyền truy cập tài nguyên này trên GitHub."
                        )

                    # 4. 429 Too Many Requests
                    if response.status_code == 429:
                        retry_after_str = response.headers.get("retry-after")
                        retry_after = int(retry_after_str) if retry_after_str else None
                        raise GitHubRateLimitError(
                            "GitHub API trả về 429 Too Many Requests.",
                            retry_after=retry_after,
                        )

                    # 5. 404 Not Found
                    if response.status_code == 404:
                        raise GitHubNotFoundError(
                            "Không tìm thấy tài nguyên trên GitHub."
                        )

                    # 6. 409 Conflict (Empty Repository hoặc conflict)
                    if response.status_code == 409:
                        msg = ""
                        try:
                            data = response.json()
                            msg = (
                                data.get("message", "")
                                if isinstance(data, dict)
                                else str(data)
                            )
                        except Exception:
                            msg = response.text
                        if "empty" in msg.lower() or "commits" in url:
                            raise GitHubEmptyRepositoryError("Git repository is empty.")
                        raise GitHubApiError(
                            f"GitHub API trả về mã lỗi HTTP 409: {msg}"
                        )

                    # 7. 5xx Server Error (Lỗi tạm thời, có thể retry)
                    if response.status_code >= 500:
                        if attempt < self.max_retries:
                            delay = self.base_delay * (2**attempt) + random.uniform(
                                0.1, 0.5
                            )
                            logger.warning(
                                f"GitHub 5xx server error ({response.status_code}), "
                                f"retry sau {delay:.2f}s"
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise GitHubServerError(
                            f"GitHub API lỗi máy chủ (HTTP {response.status_code})."
                        )

                    # Lỗi client 4xx khác
                    raise GitHubApiError(
                        f"GitHub API trả về mã lỗi HTTP {response.status_code}."
                    )

                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt < self.max_retries:
                        delay = self.base_delay * (2**attempt) + random.uniform(
                            0.1, 0.5
                        )
                        logger.warning(
                            f"Lỗi mạng GitHub ({exc.__class__.__name__}), "
                            f"retry sau {delay:.2f}s"
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise GitHubNetworkError(
                        "Không thể kết nối tới GitHub API sau nhiều lần thử lại."
                    ) from exc

            raise GitHubNetworkError("Không thể hoàn thành yêu cầu tới GitHub API.")

        if self._client is not None:
            return await _execute(self._client)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await _execute(client)

    async def list_repositories(
        self,
        per_page: int = 100,
        max_pages: int = 50,
    ) -> list[dict[str, Any]]:
        """Lấy danh sách tất cả repositories có thể truy cập
        của tài khoản authenticated.

        Hỗ trợ phân trang chuẩn theo RFC 5988 (Link header).
        """
        repositories: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        url_or_endpoint: str | None = "/user/repos"
        params: dict[str, Any] | None = {
            "per_page": min(per_page, 100),
            "sort": "updated",
            "direction": "desc",
            "affiliation": "owner,collaborator,organization_member",
        }
        if visibility:
            params["visibility"] = visibility

        page_count = 0

        while url_or_endpoint and page_count < max_pages:
            page_count += 1
            response = await self._request("GET", url_or_endpoint, params=params)
            data = response.json()

            if not isinstance(data, list):
                raise GitHubApiError(
                    "Định dạng dữ liệu trả về từ GitHub không phải danh sách."
                )

            for repo in data:
                if isinstance(repo, dict) and "id" in repo:
                    repo_id = repo["id"]
                    if repo_id not in seen_ids:
                        seen_ids.add(repo_id)
                        repositories.append(repo)

            # Phân trang: Đọc Link header
            next_url = _parse_next_link(response.headers.get("link"))
            if next_url:
                url_or_endpoint = next_url
                params = None  # URL trong Link header đã bao gồm query params
            else:
                break

        return repositories

    async def get_repository_languages(
        self,
        owner: str,
        repo: str,
    ) -> dict[str, int]:
        """Lấy số lượng byte theo ngôn ngữ lập trình của repository.

        Giữ nguyên số byte thật từ GitHub (ví dụ: {"Python": 185000, "TypeScript":
        92000}).
        """
        try:
            response = await self._request("GET", f"/repos/{owner}/{repo}/languages")
            if response.status_code == 204:
                return {}
            data = response.json()
            if isinstance(data, dict):
                return {
                    str(k): int(v)
                    for k, v in data.items()
                    if isinstance(v, (int, float))
                }
            return {}
        except (GitHubNotFoundError, GitHubPermissionError):
            return {}

    async def get_repository_details(
        self,
        owner: str,
        repo: str,
    ) -> dict[str, Any]:
        """Lấy chi tiết repository (bao gồm parent/source nếu là fork)."""
        response = await self._request("GET", f"/repos/{owner}/{repo}")
        data = response.json()
        if not isinstance(data, dict):
            raise GitHubApiError("Thông tin chi tiết repository không hợp lệ.")
        return data

    async def get_latest_commit_sha(
        self,
        owner: str,
        repo: str,
        branch_or_ref: str = "main",
        until: datetime | None = None,
    ) -> str | None:
        """Lấy commit SHA mới nhất của branch hoặc theo mốc thời gian."""
        params: dict[str, Any] = {"sha": branch_or_ref, "per_page": 1}
        if until is not None:
            params["until"] = until.isoformat()
        try:
            response = await self._request(
                "GET", f"/repos/{owner}/{repo}/commits", params=params
            )
            data = response.json()
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                return data[0].get("sha")
            return None
        except GitHubNotFoundError:
            return None

    async def get_tree(
        self,
        owner: str,
        repo: str,
        tree_sha: str,
        recursive: bool = True,
    ) -> list[dict[str, Any]]:
        """Lấy toàn bộ cây thư mục/tập tin (Git Tree) của repository."""
        params: dict[str, Any] = {}
        if recursive:
            params["recursive"] = 1
        try:
            response = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/git/trees/{tree_sha}",
                params=params,
            )
            data = response.json()
            if (
                isinstance(data, dict)
                and "tree" in data
                and isinstance(data["tree"], list)
            ):
                return data["tree"]
            return []
        except GitHubNotFoundError:
            return []

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
        max_bytes: int = 512 * 1024,
    ) -> str | None:
        """Lấy nội dung văn bản UTF-8 của một tập tin trong repository.

        Tự động decode base64 và áp dụng giới hạn kích thước an toàn.
        """
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref
        safe_path = quote(path.lstrip("/"), safe="/")
        try:
            response = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/contents/{safe_path}",
                params=params,
            )
            data = response.json()
            if not isinstance(data, dict):
                return None
            size = data.get("size", 0)
            if size > max_bytes:
                logger.warning(
                    f"Tập tin {path} vượt quá giới hạn dung lượng "
                    f"({size} > {max_bytes} bytes)."
                )
                return None
            content_b64 = data.get("content")
            if not content_b64 or not isinstance(content_b64, str):
                return None
            decoded = base64.b64decode(content_b64.encode("ascii"))
            return decoded.decode("utf-8", errors="replace")
        except GitHubNotFoundError:
            return None
        except (ValueError, UnicodeError) as exc:
            logger.warning(f"Không thể giải mã nội dung tập tin {path}: {exc}")
            return None
