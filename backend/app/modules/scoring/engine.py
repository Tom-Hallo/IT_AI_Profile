"""Deterministic, conservative PBI-016 scoring; never infer absent activity."""

from dataclasses import dataclass

WEIGHTS = {
    "code_contribution": 30,
    "commit_frequency": 20,
    "pr_contribution": 20,
    "complexity": 20,
    "confidence": 10,
}
VERSION = "1.0.0"


@dataclass(frozen=True)
class Metric:
    value: float | None  # normalized 0..1; None means not observed
    evidence_ids: tuple[int, ...] = ()


def calculate(metrics: dict[str, Metric], *, rubric_version: str = VERSION) -> dict:
    """A score is only valid when ALL required dimensions have verified evidence.

    Missing metrics are not zero. Caller must independently verify provenance,
    authorization, and that metric normalization is based on real observations.
    """
    missing = [
        name
        for name in WEIGHTS
        if name not in metrics
        or metrics[name].value is None
        or not metrics[name].evidence_ids
    ]
    if missing:
        return {
            "status": "Insufficient",
            "score": None,
            "rubric_version": rubric_version,
            "breakdown": [],
            "missing_metrics": missing,
            "explanation": "Chưa đủ bằng chứng xác thực để đánh giá toàn bộ tiêu chí.",
        }
    breakdown = []
    for name, weight in WEIGHTS.items():
        metric = metrics[name]
        if not 0 <= metric.value <= 1:
            raise ValueError(f"Metric {name} must be normalized to [0, 1]")
        breakdown.append(
            {
                "criterion": name,
                "weight": weight,
                "normalized_value": metric.value,
                "points": round(metric.value * weight, 4),
                "evidence_ids": list(dict.fromkeys(metric.evidence_ids)),
            }
        )
    return {
        "status": "Scored",
        "score": round(sum(x["points"] for x in breakdown), 2),
        "rubric_version": rubric_version,
        "breakdown": breakdown,
        "missing_metrics": [],
        "explanation": "Điểm được tính từ 5 tiêu chí có evidence xác thực.",
    }
