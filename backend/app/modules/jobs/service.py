"""Service điều phối quy trình phân tích JD từ Text hoặc URL (PBI-025)."""

from __future__ import annotations

import logging

from app.modules.jobs.extractor import JDSkillExtractor
from app.modules.jobs.schemas import (
    ExtractedSkill,
    InputSourceType,
    JDAnalysisRequest,
    JDAnalysisResponse,
    JDFallbackSuggestion,
    JDPreviewUpdateRequest,
    JDPreviewUpdateResponse,
)
from app.modules.jobs.url_fetcher import URLFetchError, fetch_jd_from_url

logger = logging.getLogger(__name__)


class JDAnalysisService:
    """Service xử lý nghiệp vụ phân tích và chỉnh sửa preview JD."""

    def __init__(self, extractor: JDSkillExtractor | None = None) -> None:
        self.extractor = extractor or JDSkillExtractor()

    def analyze(self, req: JDAnalysisRequest) -> JDAnalysisResponse:
        """Phân tích JD từ request (text hoặc URL)."""
        warnings: list[str] = []
        raw_text: str = ""
        source_type: InputSourceType
        source_ref: str | None = None
        fallback: JDFallbackSuggestion | None = None

        if req.url is not None:
            source_type = InputSourceType.URL
            url_str = str(req.url)
            source_ref = url_str

            try:
                raw_text = fetch_jd_from_url(url_str)
            except URLFetchError as exc:
                logger.warning("Không thể fetch URL '%s': %s", url_str, exc.message)
                if req.text and req.text.strip():
                    raw_text = req.text.strip()
                    warnings.append(
                        f"Không thể tải URL ({exc.message}). Đã dùng văn bản dán sẵn."
                    )
                else:
                    return JDAnalysisResponse(
                        source_type=InputSourceType.URL,
                        source_ref=url_str,
                        raw_content_preview="",
                        title_detected=None,
                        required_skills=[],
                        preferred_skills=[],
                        total_skills_count=0,
                        warnings=[exc.message],
                        fallback=JDFallbackSuggestion(
                            fallback_mode="paste_text",
                            message=exc.message,
                            target_url=url_str,
                        ),
                    )
        elif req.text and req.text.strip():
            source_type = InputSourceType.RAW_TEXT
            raw_text = req.text.strip()
            source_ref = "raw_text"
        else:
            raise ValueError(
                "Vui lòng cung cấp nội dung văn bản JD hoặc đường dẫn URL hợp lệ."
            )

        title_detected = self.extractor.extract_title(raw_text) or req.role_hint
        required_skills, preferred_skills = self.extractor.extract_skills(raw_text)

        preview = raw_text[:300].replace("\n", " ").strip()
        if len(raw_text) > 300:
            preview += "..."

        if not required_skills and not preferred_skills:
            warnings.append(
                "Không phát hiện được kỹ năng rõ ràng nào. Bạn có thể tự bổ sung bằng "
                "tính năng chỉnh sửa preview."
            )

        return JDAnalysisResponse(
            source_type=source_type,
            source_ref=source_ref,
            raw_content_preview=preview,
            title_detected=title_detected,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            total_skills_count=len(required_skills) + len(preferred_skills),
            warnings=warnings,
            fallback=fallback,
        )

    @staticmethod
    def update_preview(req: JDPreviewUpdateRequest) -> JDPreviewUpdateResponse:
        """Cập nhật lại danh sách skills sau khi người dùng chỉnh sửa."""
        seen_keys: set[str] = set()
        clean_req: list[ExtractedSkill] = []
        for s in req.required_skills:
            if s.skill_key not in seen_keys:
                seen_keys.add(s.skill_key)
                clean_req.append(s)

        clean_pref: list[ExtractedSkill] = []
        for s in req.preferred_skills:
            if s.skill_key not in seen_keys:
                seen_keys.add(s.skill_key)
                clean_pref.append(s)

        return JDPreviewUpdateResponse(
            updated=True,
            required_skills=clean_req,
            preferred_skills=clean_pref,
            total_skills_count=len(clean_req) + len(clean_pref),
        )
