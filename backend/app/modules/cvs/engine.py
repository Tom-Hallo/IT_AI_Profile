"""Engine phÃ¢n tÃ­ch bá»‘ cá»¥c CV vÃ  chá»‘ng sao chÃ©p (Anti-Plagiarism) (PBI-032)."""

from __future__ import annotations

import re

from app.modules.cvs.schemas import (
    GeneratedResumeSection,
    LayoutSection,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
    ResumePatternSuggestion,
    TargetRole,
)

ROLE_PATTERNS: dict[TargetRole, dict[str, any]] = {
    TargetRole.BACKEND: {
        "layout": [
            LayoutSection(
                section_name="Professional Summary",
                purpose="TÃ³m táº¯t ngáº¯n gá»n sá»‘ nÄƒm kinh nghiá»‡m vÃ  tech stack chá»§ lá»±c.",
                recommended_order=1,
            ),
            LayoutSection(
                section_name="Technical Skills",
                purpose="PhÃ¢n nhÃ³m: Languages, Frameworks, Databases, Cloud & DevOps.",
                recommended_order=2,
            ),
            LayoutSection(
                section_name="Work Experience & System Projects",
                purpose="Táº­p trung vÃ o kiáº¿n trÃºc há»‡ thá»‘ng, scale vÃ  reliability.",
                recommended_order=3,
                bullet_style="STAR + System Metrics (Throughput, Latency, Uptime)",
            ),
            LayoutSection(
                section_name="Education & Certifications",
                purpose="Báº±ng cáº¥p chuyÃªn ngÃ nh vÃ  cÃ¡c chá»©ng chá»‰ ká»¹ thuáº­t.",
                recommended_order=4,
            ),
        ],
        "explanation": "Backend Ä‘Ã²i há»i minh báº¡ch vá» cáº¥u trÃºc dá»¯ liá»‡u vÃ  scalability.",
        "focus": [
            "API Design",
            "Database Optimization",
            "System Architecture",
            "Microservices",
        ],
    },
    TargetRole.FRONTEND: {
        "layout": [
            LayoutSection(
                section_name="Professional Summary",
                purpose="NÄƒng lá»±c xÃ¢y dá»±ng UX, tá»‘i Æ°u web vÃ  component design system.",
                recommended_order=1,
            ),
            LayoutSection(
                section_name="Core Tech Stack",
                purpose="TypeScript, React/Vue, State Management, CSS/Tailwind.",
                recommended_order=2,
            ),
            LayoutSection(
                section_name="Featured Projects & UI Experience",
                purpose="MÃ´ táº£ cÃ¡c giao diá»‡n phá»©c táº¡p vÃ  Web Performance metrics.",
                recommended_order=3,
                bullet_style="STAR + Web Performance Metrics",
            ),
            LayoutSection(
                section_name="Education",
                purpose="Báº±ng cáº¥p há»c thuáº­t vÃ  hoáº¡t Ä‘á»™ng chuyÃªn mÃ´n.",
                recommended_order=4,
            ),
        ],
        "explanation": "Frontend cáº§n lÃ m ná»•i báº­t tráº£i nghiá»‡m ngÆ°á»i dÃ¹ng vÃ  component.",
        "focus": ["Component Reusability", "Performance Tuning", "Modern UI"],
    },
    TargetRole.DEVOPS: {
        "layout": [
            LayoutSection(
                section_name="Summary & Infrastructure Impact",
                purpose="Má»©c Ä‘á»™ tá»± Ä‘á»™ng hÃ³a háº¡ táº§ng, CI/CD pipelines vÃ  cloud spend.",
                recommended_order=1,
            ),
            LayoutSection(
                section_name="Tools & Cloud Platforms",
                purpose="Kubernetes, Docker, Terraform, AWS/GCP, Monitoring.",
                recommended_order=2,
            ),
            LayoutSection(
                section_name="Production Infrastructure Experience",
                purpose="MÃ´ táº£ kiáº¿n trÃºc IaC, quy trÃ¬nh deployment Zero-downtime.",
                recommended_order=3,
                bullet_style="Action + Automation Metrics + Uptime/Recovery Time",
            ),
            LayoutSection(
                section_name="Certifications",
                purpose="Chá»©ng chá»‰ Cloud / Kubernetes (CKA, CKAD, AWS Architect).",
                recommended_order=4,
            ),
        ],
        "explanation": "DevOps nháº¥n máº¡nh vÃ o Ä‘á»™ á»•n Ä‘á»‹nh vÃ  tá»± Ä‘á»™ng hoÃ¡ IaC.",
        "focus": ["IaC Automation", "CI/CD Pipeline", "High Availability & Monitoring"],
    },
}


def tokenize_words(text: str) -> list[str]:
    """TÃ¡ch tá»« chuáº©n hoÃ¡ dáº¡ng chá»¯ thÆ°á»ng vÃ  bá» kÃ½ tá»± Ä‘áº·c biá»‡t."""
    return re.findall(r"\w+", text.lower())


def compute_ngram_jaccard_similarity(text1: str, text2: str, n: int = 3) -> float:
    """TÃ­nh chá»‰ sá»‘ tÆ°Æ¡ng Ä‘á»“ng Jaccard dá»±a trÃªn n-gram giá»¯a 2 Ä‘oáº¡n vÄƒn báº£n."""
    words1 = tokenize_words(text1)
    words2 = tokenize_words(text2)

    if len(words1) < n or len(words2) < n:
        s1 = set(words1)
        s2 = set(words2)
        if not s1 or not s2:
            return 0.0
        return len(s1 & s2) / len(s1 | s2)

    ngrams1 = {" ".join(words1[i : i + n]) for i in range(len(words1) - n + 1)}
    ngrams2 = {" ".join(words2[i : i + n]) for i in range(len(words2) - n + 1)}

    intersection = ngrams1 & ngrams2
    union = ngrams1 | ngrams2
    return len(intersection) / len(union) if union else 0.0


def check_exact_chunk_copy(
    source_text: str, target_text: str, min_words: int = 7
) -> bool:
    """Kiá»ƒm tra cÃ³ báº¥t ká»³ Ä‘oáº¡n copy nguyÃªn vÄƒn tá»« 7 tá»« trá»Ÿ lÃªn khÃ´ng."""
    words = tokenize_words(source_text)
    target_norm = " " + " ".join(tokenize_words(target_text)) + " "

    for i in range(len(words) - min_words + 1):
        chunk = " " + " ".join(words[i : i + min_words]) + " "
        if chunk in target_norm:
            return True
    return False


class ResumePatternEngine:
    """Engine phÃ¢n tÃ­ch pattern vÃ  sinh CV gá»‘c an toÃ n."""

    @staticmethod
    def get_pattern_suggestion(role: TargetRole) -> ResumePatternSuggestion:
        info = ROLE_PATTERNS.get(role, ROLE_PATTERNS[TargetRole.BACKEND])
        return ResumePatternSuggestion(
            target_role=role,
            recommended_layout=info["layout"],
            explanation=info["explanation"],
            key_highlights_focus=info["focus"],
        )

    @staticmethod
    def extract_layout_from_reference(ref_text: str) -> list[str]:
        """Nháº­n diá»‡n cÃ¡c má»¥c/sections chÃ­nh trong CV tham kháº£o."""
        section_patterns = [
            r"^(summary|objective|tÃ³m táº¯t|giá»›i thiá»‡u)",
            r"^(experience|kinh nghiá»‡m|work history|dá»± Ã¡n|projects)",
            r"^(skills|ká»¹ nÄƒng|technical skills|chuyÃªn mÃ´n)",
            r"^(education|há»c váº¥n|báº±ng cáº¥p)",
            r"^(certifications|chá»©ng chá»‰)",
        ]
        detected = []
        for line in ref_text.splitlines():
            line_str = line.strip()
            if not line_str or len(line_str) > 60:
                continue
            for pat in section_patterns:
                if re.search(pat, line_str, re.IGNORECASE):
                    if line_str not in detected:
                        detected.append(line_str)
                    break
        return detected or ["Summary", "Experience", "Skills", "Education"]

    def generate_original_resume(
        self, req: ResumeGenerateRequest
    ) -> ResumeGenerateResponse:
        """Táº¡o CV gá»‘c hoÃ n toÃ n tá»« verified facts cá»§a user, cháº·n sao chÃ©p."""
        if req.reference_template_text and not req.has_reference_permission:
            raise PermissionError(
                "Báº¡n chÆ°a xÃ¡c nháº­n quyá»n há»£p phÃ¡p sá»­ dá»¥ng tÃ i liá»‡u tham kháº£o nÃ y."
            )

        facts_by_type: dict[str, list[str]] = {}
        for f in req.verified_facts:
            facts_by_type.setdefault(f.fact_type.lower(), []).append(f.content)

        skills_summary = ", ".join(facts_by_type.get("skill", ["Software Development"]))
        summary = (
            f"Dedicated {req.target_role.value} with expertise in {skills_summary}. "
            "Delivering high-impact solutions backed by verified achievements."
        )

        sections: list[GeneratedResumeSection] = []

        if "skill" in facts_by_type:
            sections.append(
                GeneratedResumeSection(
                    title="Verified Technical Competencies",
                    bullets=[f"Proficient in: {', '.join(facts_by_type['skill'])}"],
                )
            )

        if "project" in facts_by_type:
            bullets = [
                f"Developed and maintained: {proj} (verified code contributions)"
                for proj in facts_by_type["project"]
            ]
            sections.append(
                GeneratedResumeSection(
                    title="Key Verified Projects & Systems",
                    bullets=bullets,
                )
            )

        if "metric" in facts_by_type:
            sections.append(
                GeneratedResumeSection(
                    title="Performance & Engineering Metrics",
                    bullets=facts_by_type["metric"],
                )
            )

        full_generated_text = (
            summary + "\n" + "\n".join(b for sec in sections for b in sec.bullets)
        )

        similarity = 0.0
        plagiarism = False

        if req.reference_template_text:
            similarity = compute_ngram_jaccard_similarity(
                req.reference_template_text, full_generated_text, n=3
            )
            exact_copied = check_exact_chunk_copy(
                req.reference_template_text, full_generated_text, min_words=7
            )

            if similarity > 0.20 or exact_copied:
                plagiarism = True
                raise ValueError(
                    f"Dáº¥u hiá»‡u sao chÃ©p ná»™i dung tá»« reference ({similarity:.1%}). "
                    "Há»‡ thá»‘ng chá»‰ há»— trá»£ há»c cáº¥u trÃºc bá»‘ cá»¥c, khÃ´ng sao chÃ©p cÃ¢u tá»«."
                )

        return ResumeGenerateResponse(
            target_role=req.target_role,
            summary=summary,
            sections=sections,
            similarity_with_reference=similarity,
            plagiarism_detected=plagiarism,
            source_facts_used_count=len(req.verified_facts),
        )

