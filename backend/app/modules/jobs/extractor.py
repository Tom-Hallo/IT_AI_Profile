"""Engine phân tích văn bản JD và trích xuất skills (PBI-025).

1. Phát hiện tiêu đề công việc (Job Title).
2. Tách các phân đoạn văn bản (Requirements vs Preferred).
3. Nhận diện và chuẩn hoá các kỹ năng (Canonical Skill Key).
4. Gán confidence, level và đoạn ngữ cảnh trích xuất.
"""

from __future__ import annotations

import re
from typing import Final

from app.modules.jobs.schemas import ExtractedSkill, SkillRequirementLevel

REQUIRED_PATTERNS: Final[list[str]] = [
    r"yêu cầu( bắt buộc)?",
    r"yêu cầu công việc",
    r"kỹ năng bắt buộc",
    r"requirements?",
    r"must[ -]haves?",
    r"what you need",
    r"qualifications?",
    r"minimum qualifications?",
    r"core skills?",
    r"responsibilities",
]

PREFERRED_PATTERNS: Final[list[str]] = [
    r"điểm cộng",
    r"yêu cầu ưu tiên",
    r"ưu tiên",
    r"kỹ năng ưu tiên",
    r"nice[ -]to[ -]haves?",
    r"preferred qualifications?",
    r"preferred",
    r"bonus points?",
    r"plus",
    r"good to have",
    r"additional skills?",
]

SKILL_TAXONOMY: Final[dict[str, list[str]]] = {
    # Ngôn ngữ lập trình
    "python": [r"\bpython\b", r"\bpython3\b"],
    "typescript": [r"\btypescript\b", r"\bts\b"],
    "javascript": [r"\bjavascript\b", r"\bjs\b", r"\bes6\b"],
    "java": [r"\bjava\b(?!script)"],
    "golang": [r"\bgolang\b", r"\bgo language\b"],
    "rust": [r"\brust\b"],
    "csharp": [r"\bc#\b", r"\bcsharp\b", r"\b\.net\b", r"\bdotnet\b"],
    "cpp": [r"\bc\+\+\b", r"\bcpp\b"],
    "php": [r"\bphp\b"],
    "kotlin": [r"\bkotlin\b"],
    "swift": [r"\bswift\b"],
    "sql": [r"\bsql\b"],
    # Backend Frameworks
    "fastapi": [r"\bfastapi\b"],
    "django": [r"\bdjango\b"],
    "flask": [r"\bflask\b"],
    "nodejs": [r"\bnode\.?js\b", r"\bnode\b"],
    "express": [r"\bexpress\.?js\b", r"\bexpress\b"],
    "nestjs": [r"\bnest\.?js\b", r"\bnestjs\b"],
    "springboot": [r"\bspring boot\b", r"\bspring\b"],
    # Frontend Frameworks & Tools
    "react": [r"\breact\b", r"\breact\.?js\b", r"\breact native\b"],
    "vue": [r"\bvue\b", r"\bvue\.?js\b", r"\bvuejs\b"],
    "nextjs": [r"\bnext\.?js\b", r"\bnextjs\b"],
    "angular": [r"\bangular\b"],
    "tailwind": [r"\btailwind\b", r"\btailwindcss\b"],
    # Database & Cache
    "postgresql": [r"\bpostgresql\b", r"\bpostgres\b"],
    "mysql": [r"\bmysql\b"],
    "mongodb": [r"\bmongodb\b", r"\bmongo\b"],
    "redis": [r"\bredis\b"],
    "elasticsearch": [r"\belasticsearch\b", r"\belastic search\b"],
    "sqlite": [r"\bsqlite\b"],
    # DevOps & Infrastructure
    "docker": [r"\bdocker\b"],
    "kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "aws": [r"\baws\b", r"\bamazon web services\b"],
    "gcp": [r"\bgcp\b", r"\bgoogle cloud\b"],
    "azure": [r"\bazure\b"],
    "cicd": [r"\bci/cd\b", r"\bci-cd\b", r"\bcontinuous integration\b"],
    "git": [r"\bgit\b", r"\bgithub\b", r"\bgitlab\b"],
    "terraform": [r"\bterraform\b"],
    "linux": [r"\blinux\b", r"\bubuntu\b"],
    # Architecture & Practices
    "rest_api": [r"\brest\b", r"\brestful\b", r"\brest api\b", r"\bapi\b"],
    "graphql": [r"\bgraphql\b"],
    "microservices": [r"\bmicroservices\b", r"\bmicro-services\b"],
    "unit_testing": [r"\bunit test(ing)?\b", r"\bpytest\b", r"\bjest\b"],
    "agile_scrum": [r"\bagile\b", r"\bscrum\b"],
}


class JDSkillExtractor:
    """Bộ trích xuất và phân loại kỹ năng từ JD."""

    def __init__(self, taxonomy: dict[str, list[str]] | None = None) -> None:
        self.taxonomy = taxonomy or SKILL_TAXONOMY

    def extract_title(self, text: str) -> str | None:
        """Nhận diện chức danh công việc từ những dòng đầu tiên."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None

        title_keywords = [
            "developer",
            "engineer",
            "programmer",
            "architect",
            "lead",
            "manager",
            "intern",
            "fresher",
            "junior",
            "senior",
            "chuyên viên",
            "kỹ sư",
            "lập trình viên",
        ]
        for line in lines[:5]:
            low = line.lower()
            if any(kw in low for kw in title_keywords) and len(line) < 100:
                cleaned = re.sub(
                    r"^(job title|title|position|vị trí( tuyển dụng)?)\s*[:\-]\s*",
                    "",
                    line,
                    flags=re.IGNORECASE,
                )
                return cleaned.strip()

        return lines[0][:80] if len(lines[0]) < 80 else None

    def segment_text(self, text: str) -> tuple[str, str, str]:
        """Tách văn bản: (general, required, preferred)."""
        lines = text.splitlines()
        current_section = "general"
        general_lines: list[str] = []
        required_lines: list[str] = []
        preferred_lines: list[str] = []

        req_re = re.compile(
            r"^(#+|\d+\.|\*|-)?\s*(" + "|".join(REQUIRED_PATTERNS) + r")\s*[:\-]?",
            re.IGNORECASE,
        )
        pref_re = re.compile(
            r"^(#+|\d+\.|\*|-)?\s*(" + "|".join(PREFERRED_PATTERNS) + r")\s*[:\-]?",
            re.IGNORECASE,
        )

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            if pref_re.search(line_str):
                current_section = "preferred"
                preferred_lines.append(line_str)
                continue
            elif req_re.search(line_str):
                current_section = "required"
                required_lines.append(line_str)
                continue

            if current_section == "preferred":
                preferred_lines.append(line_str)
            elif current_section == "required":
                required_lines.append(line_str)
            else:
                general_lines.append(line_str)

        return (
            "\n".join(general_lines),
            "\n".join(required_lines),
            "\n".join(preferred_lines),
        )

    def extract_skills(
        self, text: str
    ) -> tuple[list[ExtractedSkill], list[ExtractedSkill]]:
        """Trích xuất danh sách skills tách thành (required, preferred)."""
        gen_text, req_text, pref_text = self.segment_text(text)

        required_skills: dict[str, ExtractedSkill] = {}
        preferred_skills: dict[str, ExtractedSkill] = {}

        for skill_key, patterns in self.taxonomy.items():
            compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

            pref_match, pref_snippet = self._find_first_match(
                compiled_patterns, pref_text
            )
            req_match, req_snippet = self._find_first_match(compiled_patterns, req_text)
            gen_match, gen_snippet = None, None
            if not pref_match and not req_match:
                gen_match, gen_snippet = self._find_first_match(
                    compiled_patterns, gen_text
                )

            if pref_match:
                preferred_skills[skill_key] = ExtractedSkill(
                    skill_key=skill_key,
                    raw_name=pref_match,
                    level=SkillRequirementLevel.PREFERRED,
                    confidence=0.95,
                    context_snippet=pref_snippet,
                )
            elif req_match:
                required_skills[skill_key] = ExtractedSkill(
                    skill_key=skill_key,
                    raw_name=req_match,
                    level=SkillRequirementLevel.REQUIRED,
                    confidence=0.95,
                    context_snippet=req_snippet,
                )
            elif gen_match:
                required_skills[skill_key] = ExtractedSkill(
                    skill_key=skill_key,
                    raw_name=gen_match,
                    level=SkillRequirementLevel.REQUIRED,
                    confidence=0.80,
                    context_snippet=gen_snippet,
                )

        return list(required_skills.values()), list(preferred_skills.values())

    @staticmethod
    def _find_first_match(
        patterns: list[re.Pattern], text_block: str
    ) -> tuple[str | None, str | None]:
        """Tìm pattern đầu tiên trong text: (raw_name, context_snippet)."""
        if not text_block:
            return None, None

        for line in text_block.splitlines():
            for p in patterns:
                m = p.search(line)
                if m:
                    raw_name = m.group(0)
                    start = max(0, m.start() - 30)
                    end = min(len(line), m.end() + 50)
                    snippet = line[start:end].strip()
                    return raw_name, snippet

        return None, None
