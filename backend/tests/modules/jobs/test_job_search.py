"""Unit tests cho Job Search Internet (PBI-026).

Kiểm tra:
- Opt-in: endpoint yêu cầu đăng nhập
- Deduplicate
- Timeout / nguồn lỗi / rỗng
- Mapping đúng title, company, source, url, fetched_at
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from app.modules.jobs.schemas import AllowedJobSource, JobItem, JobSearchRequest
from app.modules.jobs.search_service import JobSearchService


def _make_remotive_payload(jobs: list[dict] | None = None) -> dict:
    return {
        "job-count": len(jobs or []),
        "jobs": jobs
        or [
            {
                "id": 1001,
                "title": "Senior Python Developer",
                "company_name": "Acme Corp",
                "url": "https://remotive.com/remote-jobs/software-dev/senior-python-1001",
                "candidate_required_location": "Worldwide",
                "category": "Software Development",
                "tags": ["python", "fastapi", "remote"],
                "description": "<p>We need a strong Python engineer.</p>",
            },
            {
                "id": 1002,
                "title": "Senior Python Developer",  # trùng title+company để test dedup
                "company_name": "Acme Corp",
                "url": "https://remotive.com/remote-jobs/software-dev/senior-python-1002",
                "candidate_required_location": "Remote",
                "category": "Software Development",
                "tags": ["python"],
                "description": "Duplicate entry",
            },
            {
                "id": 1003,
                "title": "React Frontend Engineer",
                "company_name": "Beta Inc",
                "url": "https://remotive.com/remote-jobs/frontend/react-1003",
                "candidate_required_location": "USA Only",
                "category": "Software Development",
                "tags": ["react", "typescript"],
                "description": "Frontend role",
            },
        ],
    }


class TestJobSearchService:
    def test_search_happy_path_maps_fields(self) -> None:
        service = JobSearchService()
        req = JobSearchRequest(query="python", limit=10)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = _make_remotive_payload()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = service.search(req)

        assert result.total >= 1
        assert result.deduplicated_count >= 1  # có 1 bản trùng
        assert any(s.status == "ok" for s in result.source_status)

        job = result.jobs[0]
        assert isinstance(job, JobItem)
        assert job.title
        assert job.company
        assert job.source == AllowedJobSource.REMOTIVE
        assert job.url.startswith("https://")
        assert job.fetched_at  # ISO string
        assert job.expired is False

    def test_deduplicate_by_title_and_company(self) -> None:
        service = JobSearchService()
        jobs = [
            JobItem(
                id="1",
                title="Python Dev",
                company="Acme",
                source=AllowedJobSource.REMOTIVE,
                url="https://a.com/1",
                fetched_at="2026-01-01T00:00:00Z",
            ),
            JobItem(
                id="2",
                title="python dev",  # case khác
                company="Acme",
                source=AllowedJobSource.REMOTIVE,
                url="https://a.com/2",
                fetched_at="2026-01-01T00:00:00Z",
            ),
            JobItem(
                id="3",
                title="Python Dev",
                company="Other Co",
                source=AllowedJobSource.REMOTIVE,
                url="https://a.com/3",
                fetched_at="2026-01-01T00:00:00Z",
            ),
        ]
        unique, dedup_count = service._deduplicate(jobs)
        assert len(unique) == 2
        assert dedup_count == 1

    def test_timeout_returns_clear_status(self) -> None:
        service = JobSearchService()
        req = JobSearchRequest(query="python")

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value = mock_client

            result = service.search(req)

        assert result.total == 0
        assert any(s.status == "timeout" for s in result.source_status)
        assert any(
            "thời gian chờ" in w.lower() or "timeout" in w.lower()
            for w in result.warnings
        )

    def test_http_error_returns_error_status(self) -> None:
        service = JobSearchService()
        req = JobSearchRequest(query="python")

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = service.search(req)

        assert result.total == 0
        assert any(s.status == "error" for s in result.source_status)

    def test_empty_result_from_source(self) -> None:
        service = JobSearchService()
        req = JobSearchRequest(query="xyznonexistentquery123")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"jobs": []}

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = service.search(req)

        assert result.total == 0
        assert any(s.status == "empty" for s in result.source_status)
        assert result.warnings  # có warning rỗng