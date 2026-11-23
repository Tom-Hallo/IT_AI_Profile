"""Deterministic, conservative PBI-016 scoring; never infer absent activity."""

import math
from collections.abc import Mapping
from dataclasses import dataclass

WEIGHTS = {
    "code_contribution": 30,
    "commit_frequency": 20,
    "pr_contribution": 20,
    "complexity": 20,
    "confidence": 10,
}
VERSION = "1.0.0"

# Framework rubric v2.2 has no mandatory PR/commit split: a verified PR or a
# verified non-merge commit can prove a framework contribution independently.
FRAMEWORK_WEIGHTS = {
    "code_contribution": 40,
    "complexity": 20,
    "verified_activity": 30,
    "confidence": 10,
}


@dataclass(frozen=True)
class Metric:
    value: float | None  # normalized 0..1; None means not observed
    evidence_ids: tuple[int, ...] = ()


def calculate(
    metrics: dict[str, Metric],
    *,
    rubric_version: str = VERSION,
    weights: Mapping[str, int] | None = None,
) -> dict:
    """A score is only valid when ALL required dimensions have verified evidence.

    Missing metrics are not zero. Caller must independently verify provenance,
    authorization, and that metric normalization is based on real observations.
    """
    active_weights = dict(WEIGHTS if weights is None else weights)
    if (
        set(active_weights) != set(WEIGHTS)
        or any(type(value) is not int or value < 0 for value in active_weights.values())
        or sum(active_weights.values()) != 100
    ):
        raise ValueError(
            "Rubric weights must contain five nonnegative integer weights totaling 100"
        )
    for name, metric in metrics.items():
        if name in active_weights and metric.value is not None:
            if not math.isfinite(metric.value) or not 0 <= metric.value <= 1:
                raise ValueError(f"Metric {name} must be normalized to [0, 1]")
    missing = [
        name
        for name in active_weights
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
    for name, weight in active_weights.items():
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


def calculate_framework(
    metrics: dict[str, Metric],
    *,
    rubric_version: str,
    weights: Mapping[str, int] | None = None,
) -> dict:
    """Score framework contributions from source-linked verified GitHub events.

    Never assign absent activity a numeric zero: all four criteria must be backed
    by actual source-file contributions and their verified event references.
    Event count uses commit OR PR evidence, not a fabricated counterpart.
    """
    active_weights = dict(FRAMEWORK_WEIGHTS if weights is None else weights)
    if (
        set(active_weights) != set(FRAMEWORK_WEIGHTS)
        or any(
            type(weight) is not int or weight < 0
            for weight in active_weights.values()
        )
        or sum(active_weights.values()) != 100
    ):
        raise ValueError(
            "Framework rubric must have four nonnegative weights totaling 100"
        )
    missing = [
        name
        for name in active_weights
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
            "explanation": (
                "Chưa có đóng góp framework được xác minh trên tệp mã nguồn."
            ),
        }

    breakdown = []
    for name, weight in active_weights.items():
        metric = metrics[name]
        if not math.isfinite(metric.value) or not 0 <= metric.value <= 1:
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
        "score": round(sum(part["points"] for part in breakdown), 2),
        "rubric_version": rubric_version,
        "breakdown": breakdown,
        "missing_metrics": [],
        "explanation": (
            "Đánh giá dựa trên đóng góp GitHub đã xác minh "
            "tại tệp sử dụng framework."
        ),
    }
