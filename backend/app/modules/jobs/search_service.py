"""Service tìm việc trên Internet theo yêu cầu người dùng (PBI-026).

Quy tắc:
- Chỉ chạy khi người dùng chủ động gửi request (opt-in).
- Chỉ lấy tin từ nguồn/API nằm trong whitelist (Remotive).
- Trả title, company, source, link gốc, thời điểm lấy tin.
- Khử trùng lặp theo (title + company) normalized.
- Xử lý rõ ràng: timeout, nguồn lỗi, rỗng, hết hạn.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from app.modules.jobs.schemas import (
    AllowedJobSource,
    JobItem,
    JobSearchRequest,
    JobSearchResponse,
    SourceStatus,
)

logger = logging.getLogger(__name__)

# Timeout ngắn để tránh treo request
SOURCE_TIMEOUT_SECONDS = 10.0
REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"


class JobSearchService:
    """Điều phối tìm việc từ các nguồn được phép."""

    def search(self, req: JobSearchRequest) -> JobSearchResponse:
        """Thực hiện tìm kiếm opt-in theo tiêu chí người dùng."""
        searched_at = datetime.now(UTC).isoformat()
        all_jobs: list[JobItem] = []
        source_statuses: list[SourceStatus] = []
        warnings: list[str] = []

        # Chỉ xử lý các nguồn nằm trong whitelist của request
        requested_sources = list(dict.fromkeys(req.sources))  # giữ thứ tự, bỏ trùng

        for source in requested_sources:
            if source == AllowedJobSource.REMOTIVE:
                jobs, status = self._fetch_remotive(req)
                all_jobs.extend(jobs)
                source_statuses.append(status)
                if status.status != "ok":
                    warnings.append(
                        f"Nguồn {source.value}: {status.message or status.status}"
                    )
            else:
                # Phòng thủ: nếu enum được mở rộng nhưng chưa implement
                source_statuses.append(
                    SourceStatus(
                        source=source,
                        status="invalid",
                        message=f"Nguồn '{source.value}' chưa được hỗ trợ.",
                        jobs_found=0,
                    )
                )
                warnings.append(f"Nguồn {source.value} không được hỗ trợ.")

        # Khử trùng lặp
        unique_jobs, dedup_count = self._deduplicate(all_jobs)

        # Giới hạn số lượng
        limited = unique_jobs[: req.limit]

        if not limited and not warnings:
            warnings.append(
                "Không tìm thấy tin tuyển dụng phù hợp với tiêu chí hiện tại."
            )

        return JobSearchResponse(
            jobs=limited,
            total=len(limited),
            deduplicated_count=dedup_count,
            source_status=source_statuses,
            warnings=warnings,
            searched_at=searched_at,
        )

    def _fetch_remotive(
        self, req: JobSearchRequest
    ) -> tuple[list[JobItem], SourceStatus]:
        """Gọi Remotive public API (không cần API key)."""
        params: dict[str, Any] = {
            "search": req.query.strip(),
            "limit": min(req.limit * 2, 50),  # lấy dư để còn chỗ sau dedup
        }
        # Remotive hỗ trợ category, nhưng search text là chính

        try:
            with httpx.Client(timeout=SOURCE_TIMEOUT_SECONDS) as client:
                response = client.get(REMOTIVE_API_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            logger.warning("Remotive timeout sau %ss", SOURCE_TIMEOUT_SECONDS)
            return [], SourceStatus(
                source=AllowedJobSource.REMOTIVE,
                status="timeout",
                message=f"Nguồn Remotive timeout ({SOURCE_TIMEOUT_SECONDS}s).",
                jobs_found=0,
            )
        except httpx.HTTPStatusError as exc:
            logger.warning("Remotive HTTP error: %s", exc)
            return [], SourceStatus(
                source=AllowedJobSource.REMOTIVE,
                status="error",
                message=f"Nguồn Remotive trả lỗi HTTP {exc.response.status_code}.",
                jobs_found=0,
            )
        except httpx.RequestError as exc:
            logger.warning("Remotive request error: %s", exc)
            return [], SourceStatus(
                source=AllowedJobSource.REMOTIVE,
                status="error",
                message=f"Không thể kết nối đến nguồn Remotive: {exc}",
                jobs_found=0,
            )
        except Exception as exc:  # phòng thủ
            logger.exception("Remotive unexpected error")
            return [], SourceStatus(
                source=AllowedJobSource.REMOTIVE,
                status="error",
                message=f"Lỗi không xác định khi gọi Remotive: {exc}",
                jobs_found=0,
            )

        jobs_raw = data.get("jobs") or []
        if not isinstance(jobs_raw, list):
            return [], SourceStatus(
                source=AllowedJobSource.REMOTIVE,
                status="error",
                message="Định dạng phản hồi từ Remotive không hợp lệ.",
                jobs_found=0,
            )

        fetched_at = datetime.now(UTC).isoformat()
        items: list[JobItem] = []

        for raw in jobs_raw:
            if not isinstance(raw, dict):
                continue

            title = (raw.get("title") or "").strip()
            company = (raw.get("company_name") or "").strip()
            url = (raw.get("url") or "").strip()

            if not title or not company or not url:
                continue

            # Remotive không có field expired rõ ràng; coi như active nếu có trong list
            expired = False

            # Tạo id ổn định
            job_id = self._make_job_id("remotive", raw.get("id"), title, company, url)

            tags: list[str] = []
            if isinstance(raw.get("tags"), list):
                tags = [str(t).strip() for t in raw["tags"] if t]
            category = raw.get("category")
            if category and str(category) not in tags:
                tags.insert(0, str(category))

            location = (raw.get("candidate_required_location") or "Remote").strip()
            # Lọc theo location nếu user chỉ định (đơn giản)
            if req.location and req.location.lower() not in ("remote", "any", ""):
                loc_lower = location.lower()
                if (
                    req.location.lower() not in loc_lower
                    and "worldwide" not in loc_lower
                    and "anywhere" not in loc_lower
                ):
                    continue

            description = raw.get("description") or ""
            preview = None
            if description:
                # Bỏ HTML thô đơn giản
                text = (
                    description.replace("<br>", " ")
                    .replace("<br/>", " ")
                    .replace("<p>", " ")
                    .replace("</p>", " ")
                )
                text = re.sub(r"<[^>]+>", " ", text)
                text = " ".join(text.split())
                preview = text[:280] + ("..." if len(text) > 280 else "")

            items.append(
                JobItem(
                    id=job_id,
                    title=title,
                    company=company,
                    source=AllowedJobSource.REMOTIVE,
                    url=url,
                    fetched_at=fetched_at,
                    location=location or "Remote",
                    tags=tags[:12],
                    expired=expired,
                    description_preview=preview,
                )
            )

        status = SourceStatus(
            source=AllowedJobSource.REMOTIVE,
            status="ok" if items else "empty",
            message=None if items else "Nguồn Remotive không trả về tin phù hợp.",
            jobs_found=len(items),
        )
        return items, status

    @staticmethod
    def _make_job_id(
        source: str,
        source_id: Any,
        title: str,
        company: str,
        url: str,
    ) -> str:
        """Tạo id ổn định cho job (ưu tiên id nguồn, fallback hash)."""
        if source_id is not None:
            return f"{source}:{source_id}"
        raw = f"{source}|{title.lower()}|{company.lower()}|{url}"
        return f"{source}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    @staticmethod
    def _deduplicate(jobs: list[JobItem]) -> tuple[list[JobItem], int]:
        """Khử trùng theo (title + company) normalized. Giữ bản đầu tiên."""
        seen: set[str] = set()
        unique: list[JobItem] = []
        for job in jobs:
            key = f"{job.title.strip().lower()}|{job.company.strip().lower()}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(job)
        dedup_count = len(jobs) - len(unique)
        return unique, dedup_count