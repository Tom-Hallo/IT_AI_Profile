"""GitHub OAuth provider integration."""

from dataclasses import dataclass

import httpx

from app.core.config import settings

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

GITHUB_TIMEOUT_SECONDS = 10.0


class GitHubOAuthError(Exception):
    """Lỗi an toàn trong quá trình giao tiếp với GitHub."""


@dataclass(frozen=True)
class GitHubIdentity:
    """Thông tin GitHub đã được xác minh."""

    provider_user_id: str
    email: str
    full_name: str
    access_token: str | None = None
    scope: str | None = None


async def get_github_identity(code: str) -> GitHubIdentity:
    """Đổi authorization code và lấy danh tính GitHub."""

    if not settings.github_oauth_enabled:
        raise GitHubOAuthError("GitHub OAuth chưa được cấu hình.")

    if not isinstance(code, str) or not code.strip():
        raise GitHubOAuthError("Authorization code không hợp lệ.")

    try:
        async with httpx.AsyncClient(timeout=GITHUB_TIMEOUT_SECONDS) as client:
            token_response = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": (settings.github_client_secret.get_secret_value()),
                    "code": code,
                    "redirect_uri": settings.github_redirect_uri,
                },
            )

            token_response.raise_for_status()
            token_data = token_response.json()

            if not isinstance(token_data, dict):
                raise GitHubOAuthError("Phản hồi token từ GitHub không hợp lệ.")

            access_token = token_data.get("access_token")

            if not isinstance(access_token, str) or not access_token.strip():
                raise GitHubOAuthError("GitHub không cấp được access token.")

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            user_response = await client.get(
                GITHUB_USER_URL,
                headers=headers,
            )
            user_response.raise_for_status()
            user_data = user_response.json()

            if not isinstance(user_data, dict):
                raise GitHubOAuthError("Thông tin tài khoản GitHub không hợp lệ.")

            github_id = user_data.get("id")
            login = user_data.get("login")
            name = user_data.get("name")

            if (
                not isinstance(github_id, int)
                or isinstance(github_id, bool)
                or not isinstance(login, str)
                or not login.strip()
            ):
                raise GitHubOAuthError("Thông tin tài khoản GitHub không hợp lệ.")

            email_response = await client.get(
                GITHUB_EMAILS_URL,
                headers=headers,
            )
            email_response.raise_for_status()
            emails = email_response.json()

            if not isinstance(emails, list):
                raise GitHubOAuthError("Danh sách email GitHub không hợp lệ.")

            verified_emails = [
                item["email"].strip().lower()
                for item in emails
                if isinstance(item, dict)
                and item.get("verified") is True
                and isinstance(item.get("email"), str)
                and item["email"].strip()
            ]

            primary_email = next(
                (
                    item["email"].strip().lower()
                    for item in emails
                    if isinstance(item, dict)
                    and item.get("verified") is True
                    and item.get("primary") is True
                    and isinstance(item.get("email"), str)
                    and item["email"].strip()
                ),
                None,
            )

            email = primary_email or (verified_emails[0] if verified_emails else None)

            if not email:
                raise GitHubOAuthError("Tài khoản GitHub không có email đã xác minh.")

            full_name = (
                name.strip()
                if isinstance(name, str) and name.strip()
                else login.strip()
            )

            return GitHubIdentity(
                provider_user_id=str(github_id),
                email=email,
                full_name=full_name,
                access_token=access_token,
                scope=token_data.get("scope") if isinstance(token_data, dict) else None,
            )

    except GitHubOAuthError:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        raise GitHubOAuthError("Không thể xác thực tài khoản với GitHub.") from None
