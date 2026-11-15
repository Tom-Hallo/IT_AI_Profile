"""Engine phân tích bố cục CV và chống sao chép (Anti-Plagiarism) (PBI-032)."""

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
                purpose="Tóm tắt ngắn gọn số năm kinh nghiệm và tech stack chủ lực.",
                recommended_order=1,
            ),
            LayoutSection(
                section_name="Technical Skills",
                purpose="Phân nhóm: Languages, Frameworks, Databases, Cloud & DevOps.",
                recommended_order=2,
            ),
            LayoutSection(
                section_name="Work Experience & System Projects",
                purpose="Tập trung vào kiến trúc hệ thống, scale và reliability.",
                recommended_order=3,
                bullet_style="STAR + System Metrics (Throughput, Latency, Uptime)",
            ),
            LayoutSection(
                section_name="Education & Certifications",
                purpose="Bằng cấp chuyên ngành và các chứng chỉ kỹ thuật.",
                recommended_order=4,
            ),
        ],
        "explanation": "Backend đòi hỏi minh bạch về cấu trúc dữ liệu và scalability.",
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
                purpose="Năng lực xây dựng UX, tối ưu web và component design system.",
                recommended_order=1,
            ),
            LayoutSection(
                section_name="Core Tech Stack",
                purpose="TypeScript, React/Vue, State Management, CSS/Tailwind.",
                recommended_order=2,
            ),
            LayoutSection(
                section_name="Featured Projects & UI Experience",
                purpose="Mô tả các giao diện phức tạp và Web Performance metrics.",
                recommended_order=3,
                bullet_style="STAR + Web Performance Metrics",
            ),
            LayoutSection(
                section_name="Education",
                purpose="Bằng cấp học thuật và hoạt động chuyên môn.",
                recommended_order=4,
            ),
        ],
        "explanation": "Frontend cần làm nổi bật trải nghiệm người dùng và component.",
        "focus": ["Component Reusability", "Performance Tuning", "Modern UI"],
    },
    TargetRole.DEVOPS: {
        "layout": [
            LayoutSection(
                section_name="Summary & Infrastructure Impact",
                purpose="Mức độ tự động hóa hạ tầng, CI/CD pipelines và cloud spend.",
                recommended_order=1,
            ),
            LayoutSection(
                section_name="Tools & Cloud Platforms",
                purpose="Kubernetes, Docker, Terraform, AWS/GCP, Monitoring.",
                recommended_order=2,
            ),
            LayoutSection(
                section_name="Production Infrastructure Experience",
                purpose="Mô tả kiến trúc IaC, quy trình deployment Zero-downtime.",
                recommended_order=3,
                bullet_style="Action + Automation Metrics + Uptime/Recovery Time",
            ),
            LayoutSection(
                section_name="Certifications",
                purpose="Chứng chỉ Cloud / Kubernetes (CKA, CKAD, AWS Architect).",
                recommended_order=4,
            ),
        ],
        "explanation": "DevOps nhấn mạnh vào độ ổn định và tự động hoá IaC.",
        "focus": ["IaC Automation", "CI/CD Pipeline", "High Availability & Monitoring"],
    },
}


def tokenize_words(text: str) -> list[str]:
    """Tách từ chuẩn hoá dạng chữ thường và bỏ ký tự đặc biệt."""
    return re.findall(r"\w+", text.lower())


def compute_ngram_jaccard_similarity(text1: str, text2: str, n: int = 3) -> float:
    """Tính chỉ số tương đồng Jaccard dựa trên n-gram giữa 2 đoạn văn bản."""
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
    """Kiểm tra có bất kỳ đoạn copy nguyên văn từ 7 từ trở lên không."""
    words = tokenize_words(source_text)
    target_norm = " " + " ".join(tokenize_words(target_text)) + " "

    for i in range(len(words) - min_words + 1):
        chunk = " " + " ".join(words[i : i + min_words]) + " "
        if chunk in target_norm:
            return True
    return False


class ResumePatternEngine:
    """Engine phân tích pattern và sinh CV gốc an toàn."""

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
        """Nhận diện các mục/sections chính trong CV tham khảo."""
        section_patterns = [
            r"^(summary|objective|tóm tắt|giới thiệu)",
            r"^(experience|kinh nghiệm|work history|dự án|projects)",
            r"^(skills|kỹ năng|technical skills|chuyên môn)",
            r"^(education|học vấn|bằng cấp)",
            r"^(certifications|chứng chỉ)",
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
        """Tạo CV gốc hoàn toàn từ verified facts của user, chặn sao chép."""
        if req.reference_template_text and not req.has_reference_permission:
            raise PermissionError(
                "Bạn chưa xác nhận quyền hợp pháp sử dụng tài liệu tham khảo này."
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
                    f"Dấu hiệu sao chép nội dung từ reference ({similarity:.1%}). "
                    "Hệ thống chỉ hỗ trợ học cấu trúc bố cục, không sao chép câu từ."
                )

        return ResumeGenerateResponse(
            target_role=req.target_role,
            summary=summary,
            sections=sections,
            similarity_with_reference=similarity,
            plagiarism_detected=plagiarism,
            source_facts_used_count=len(req.verified_facts),
        )
