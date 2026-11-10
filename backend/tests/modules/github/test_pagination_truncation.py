from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.github.client import GitHubApiClient


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method_name", "item"),
    [
        ("list_commits", {"sha": "abc123"}),
        ("list_pull_requests", {"number": 123}),
    ],
)
@pytest.mark.parametrize("has_next_page", [True, False])
async def test_pagination_truncation_callback(
    method_name,
    item,
    has_next_page,
):
    client = GitHubApiClient(access_token="fake-test-token")

    response = MagicMock()
    response.json.return_value = [item]

    if has_next_page:
        response.headers = {
            "link": (
                '<https://api.github.com/repos/example/demo/items?page=2>; rel="next"'
            )
        }
    else:
        response.headers = {}

    client._request = AsyncMock(return_value=response)

    on_truncated = MagicMock()

    method = getattr(client, method_name)
    result = await method(
        owner="example",
        repo="demo",
        max_pages=1,
        on_truncated=on_truncated,
    )

    assert result == [item]
    assert client._request.await_count == 1

    if has_next_page:
        on_truncated.assert_called_once_with()
    else:
        on_truncated.assert_not_called()
