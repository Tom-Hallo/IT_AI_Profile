"""Pydantic schemas cho GitHub API (PBI-009)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RepositoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    name: str
    full_name: str | None = None
    html_url: str
    description: str | None = None
    private: bool
    default_branch: str
    is_fork: bool
    fork_source: str | None = None
    primary_language: str | None = None
    languages: dict[str, Any] | None = None
    stars_count: int
    forks_count: int
    open_issues_count: int
    size_kb: int
    archived: bool
    disabled: bool
    pushed_at: datetime | None = None
    github_created_at: datetime | None = None
    github_updated_at: datetime | None = None
    last_synced_at: datetime | None = None
    sync_status: str


class RepositoryListResponse(BaseModel):
    items: list[RepositoryItemResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class SyncStatusResponse(BaseModel):
    status: Literal["idle", "running", "completed", "failed"]
    is_connected: bool
    has_private_scope: bool
    total_repositories: int
    last_synced_at: str | None = None
    error_message: str | None = None


class SyncTriggerResponse(BaseModel):
    status: str
    message: str
    job_id: str | None = None
    synced_count: int | None = None
    last_synced_at: str | None = None
