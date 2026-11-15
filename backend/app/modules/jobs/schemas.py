"""Pydantic schemas cho module Job Description Analysis (PBI-025).

Há»— trá»£ phÃ¢n tÃ­ch JD tá»« Text hoáº·c URL:
- PhÃ¢n loáº¡i Required vs Preferred skills
- Gáº¯n confidence score, canonical skill key, Ä‘oáº¡n trÃ­ch ngá»¯ cáº£nh
- Cho phÃ©p preview vÃ  chá»‰nh sá»­a káº¿t quáº£ trÆ°á»›c khi lÆ°u/match
- Cáº£nh bÃ¡o vÃ  fallback rÃµ rÃ ng khi URL khÃ´ng há»£p lá»‡ hoáº·c lá»—i
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, HttpUrl


class SkillRequirementLevel(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"


class InputSourceType(StrEnum):
    RAW_TEXT = "raw_text"
    URL = "url"


class ExtractedSkill(BaseModel):
    """Ká»¹ nÄƒng Ä‘Æ°á»£c trÃ­ch xuáº¥t tá»« JD."""

    skill_key: str = Field(
        ...,
        description="Canonical key chuáº©n hoÃ¡ (vd: python, fastapi, docker)",
    )
    raw_name: str = Field(
        ...,
        description="TÃªn ká»¹ nÄƒng gá»‘c tÃ¬m tháº¥y trong vÄƒn báº£n JD",
    )
    level: SkillRequirementLevel = Field(
        ...,
        description="Má»©c Ä‘á»™ yÃªu cáº§u: báº¯t buá»™c hoáº·c Æ°u tiÃªn",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Äá»™ tin cáº­y trÃ­ch xuáº¥t (0.0 - 1.0)",
    )
    context_snippet: str | None = Field(
        None,
        description="Äoáº¡n vÄƒn báº£n ngá»¯ cáº£nh chá»©a ká»¹ nÄƒng Ä‘á»ƒ ngÆ°á»i dÃ¹ng Ä‘á»‘i chiáº¿u",
    )


class JDAnalysisRequest(BaseModel):
    """Request phÃ¢n tÃ­ch JD tá»« Text hoáº·c URL."""

    text: Annotated[
        str | None,
        Field(
            None,
            max_length=50_000,
            description="Ná»™i dung vÄƒn báº£n JD thÃ´ cáº§n phÃ¢n tÃ­ch",
        ),
    ] = None
    url: Annotated[
        HttpUrl | None,
        Field(
            None,
            description="URL cÃ´ng khai cá»§a tin tuyá»ƒn dá»¥ng/JD",
        ),
    ] = None
    role_hint: Annotated[
        str | None,
        Field(
            None,
            max_length=100,
            description="Gá»£i Ã½ vá»‹ trÃ­ tuyá»ƒn dá»¥ng (náº¿u cÃ³, vd: Backend)",
        ),
    ] = None


class JDFallbackSuggestion(BaseModel):
    """ThÃ´ng tin gá»£i Ã½ fallback khi fetch URL tháº¥t báº¡i."""

    fallback_mode: str = "paste_text"
    message: str
    target_url: str | None = None


class JDAnalysisResponse(BaseModel):
    """Káº¿t quáº£ phÃ¢n tÃ­ch JD tráº£ vá» cho client."""

    source_type: InputSourceType
    source_ref: str | None = Field(None, description="URL nguá»“n hoáº·c 'raw_text'")
    raw_content_preview: str = Field(
        ...,
        description="Preview 300 kÃ½ tá»± Ä‘áº§u cá»§a vÄƒn báº£n JD",
    )
    title_detected: str | None = Field(
        None,
        description="TiÃªu Ä‘á» cÃ´ng viá»‡c Ä‘Æ°á»£c nháº­n diá»‡n tá»« JD",
    )
    required_skills: list[ExtractedSkill] = Field(default_factory=list)
    preferred_skills: list[ExtractedSkill] = Field(default_factory=list)
    total_skills_count: int
    warnings: list[str] = Field(default_factory=list)
    fallback: JDFallbackSuggestion | None = None


class JDPreviewUpdateRequest(BaseModel):
    """Request cáº­p nháº­t/chá»‰nh sá»­a danh sÃ¡ch skills sau khi preview."""

    required_skills: list[ExtractedSkill]
    preferred_skills: list[ExtractedSkill]


class JDPreviewUpdateResponse(BaseModel):
    """Káº¿t quáº£ sau khi ngÆ°á»i dÃ¹ng chá»‰nh sá»­a preview."""

    updated: bool = True
    required_skills: list[ExtractedSkill]
    preferred_skills: list[ExtractedSkill]
    total_skills_count: int

