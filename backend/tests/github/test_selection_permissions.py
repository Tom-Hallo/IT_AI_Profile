"""Unit tests that do not contact GitHub or PostgreSQL."""

import asyncio
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.modules.github import selection_service as service
from app.modules.github.selection_schemas import RepoOption, SelectionUpdate

PUBLIC = RepoOption(
    id=101,
    full_name="example/public",
    private=False,
    html_url="https://github.com/example/public",
)
PRIVATE = RepoOption(
    id=102,
    full_name="example/private",
    private=True,
    html_url="https://github.com/example/private",
)


def test_missing_private_permission(monkeypatch):
    monkeypatch.setattr(
        service, "credentials", lambda db, user_id: ("test-token", False)
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.options(Mock(), 1, "private"))
    assert exc.value.status_code == 403


def test_unowned_repository_rejected(monkeypatch):
    monkeypatch.setattr(
        service, "credentials", lambda db, user_id: ("test-token", True)
    )

    async def fake_fetch(token):
        return [PUBLIC]

    monkeypatch.setattr(service, "fetch_options", fake_fetch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.update_selection(
                Mock(), 1, SelectionUpdate(scope="combined", repository_ids=[999])
            )
        )
    assert exc.value.status_code == 403


def test_private_outside_public_scope(monkeypatch):
    monkeypatch.setattr(
        service, "credentials", lambda db, user_id: ("test-token", True)
    )

    async def fake_fetch(token):
        return [PRIVATE]

    monkeypatch.setattr(service, "fetch_options", fake_fetch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.update_selection(
                Mock(), 1, SelectionUpdate(scope="public", repository_ids=[102])
            )
        )
    assert exc.value.status_code == 422


def test_duplicate_rejected(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.update_selection(
                Mock(), 1, SelectionUpdate(scope="public", repository_ids=[101, 101])
            )
        )
    assert exc.value.status_code == 422
