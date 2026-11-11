"""Rubric configuration cho Role-based Scoring (PBI-017).

Rubric là DỮ LIỆU cấu hình có version (JSON trong ``rubrics/`` hoặc tạo bằng
code), không nằm trong logic engine. Thêm role mới = thêm một rubric, không sửa engine.

Trọng số/ngưỡng trong các rubric đi kèm là GIÁ TRỊ ĐỀ XUẤT BAN ĐẦU
(``calibration_status = "proposed_unvalidated"``), chưa được kiểm chứng như chuẩn nghề
nghiệp; cần thử nghiệm/hiệu chỉnh trước production (SRS Phụ lục B).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ai.scoring.evidence_catalog import (
    SUPPORTED_ARCHITECTURE_PATTERNS,
    normalize_key,
)
from app.ai.scoring.schemas import CriterionType

DEFAULT_RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"
WEIGHT_SUM_TOLERANCE = 1e-6

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

METHOD_SKILL_SCORE = "skill_score"
METHOD_ARCH_PATTERN_COVERAGE = "architecture_pattern_coverage"

# method -> loại criterion được phép dùng. Engine dispatch theo đúng bảng này.
SCORING_METHODS: dict[str, CriterionType] = {
    METHOD_SKILL_SCORE: CriterionType.SKILL,
    METHOD_ARCH_PATTERN_COVERAGE: CriterionType.ARCHITECTURE,
}


class RubricConfigError(ValueError):
    """Rubric sai cấu hình hoặc không tìm thấy."""


class RubricNotFoundError(RubricConfigError):
    pass


class ScoringRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str
    # SKILL: độ lệch điểm tối đa (thang 0..100) giữa các item cùng skill trước khi
    # coi là CONFLICTING. ARCHITECTURE: độ lệch confidence_score (0..1) tối đa giữa
    # các bản ghi cùng (file, classification).
    conflict_tolerance: float = Field(default=15.0, ge=0.0)
    # ARCHITECTURE: số pattern phân biệt cần để đạt 100 điểm.
    full_score_pattern_count: int | None = Field(default=None, ge=1)

    @field_validator("method")
    @classmethod
    def _known_method(cls, value: str) -> str:
        if value not in SCORING_METHODS:
            raise ValueError(f"unknown scoring method: {value}")
        return value


class MinimumEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_evidence_refs: int = Field(default=1, ge=0)
    min_distinct_patterns: int = Field(default=1, ge=0)


class ConfidenceRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Dưới ngưỡng này (thang 0..100) tiêu chí là INSUFFICIENT, không được chấm.
    min_confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    # Số evidence để đạt 100% confidence gốc; ít hơn thì confidence bị nhân tỉ lệ.
    evidence_for_full_confidence: int = Field(default=1, ge=1)


class Criterion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    type: CriterionType
    source_skill_key: str | None = None
    alternative_skill_keys: list[str] = Field(default_factory=list)
    architecture_patterns: list[str] = Field(default_factory=list)
    weight: float = Field(gt=0.0, le=1.0)
    required: bool = True
    # True: evidence đã dùng cho tiêu chí này không được dùng lại cho các tiêu chí
    # exclusive đứng sau (theo thứ tự rubric) — chống đếm trùng.
    evidence_exclusive: bool = False
    scoring_rule: ScoringRule
    minimum_evidence: MinimumEvidence = Field(default_factory=MinimumEvidence)
    confidence_rule: ConfidenceRule = Field(default_factory=ConfidenceRule)

    @field_validator("key")
    @classmethod
    def _valid_key(cls, value: str) -> str:
        if not _KEY_RE.match(value):
            raise ValueError("criterion key must match ^[a-z][a-z0-9_]*$")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if SCORING_METHODS[self.scoring_rule.method] != self.type:
            raise ValueError(
                f"method {self.scoring_rule.method!r} is not valid for type "
                f"{self.type.value}"
            )
        if self.type == CriterionType.SKILL:
            if not self.source_skill_key:
                raise ValueError("SKILL criterion requires source_skill_key")
            if self.architecture_patterns:
                raise ValueError("SKILL criterion must not set architecture_patterns")
        else:
            if self.source_skill_key or self.alternative_skill_keys:
                raise ValueError("ARCHITECTURE criterion must not set skill keys")
            if not self.architecture_patterns:
                raise ValueError("ARCHITECTURE criterion requires patterns")
            full = self.scoring_rule.full_score_pattern_count
            if full is None or full > len(set(self.architecture_patterns)):
                raise ValueError(
                    "full_score_pattern_count is required and must be <= number "
                    "of patterns"
                )
            if self.minimum_evidence.min_distinct_patterns > full:
                raise ValueError("min_distinct_patterns must be <= full count")
        return self

    @property
    def skill_keys(self) -> list[str]:
        """Danh sách skill key ứng viên (đã chuẩn hoá, giữ thứ tự, bỏ trùng)."""
        if not self.source_skill_key:
            return []
        keys = [normalize_key(self.source_skill_key)]
        keys += [normalize_key(k) for k in self.alternative_skill_keys]
        return list(dict.fromkeys(keys))

    @property
    def patterns(self) -> list[str]:
        return list(dict.fromkeys(normalize_key(p) for p in self.architecture_patterns))


class Thresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Tổng trọng số tối thiểu của các tiêu chí SCORED (0..1) mới được tính tổng điểm.
    min_coverage: float = Field(gt=0.0, le=1.0)
    confidence_high: float = Field(default=75.0, ge=0.0, le=100.0)
    confidence_medium: float = Field(default=50.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.confidence_medium > self.confidence_high:
            raise ValueError("confidence_medium must be <= confidence_high")
        return self


class RoleRubric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role_key: str
    rubric_version: str
    name: str = Field(min_length=1)
    description: str = ""
    calibration_status: Literal["proposed_unvalidated", "calibrated"] = (
        "proposed_unvalidated"
    )
    calibration_note: str = ""
    thresholds: Thresholds
    criteria: list[Criterion] = Field(min_length=1)

    @field_validator("role_key")
    @classmethod
    def _valid_role(cls, value: str) -> str:
        key = normalize_key(value)
        if not _KEY_RE.match(key):
            raise ValueError("role_key must match ^[a-z][a-z0-9_]*$")
        return key

    @field_validator("rubric_version")
    @classmethod
    def _valid_version(cls, value: str) -> str:
        if not _VERSION_RE.match(value):
            raise ValueError("rubric_version must be MAJOR.MINOR.PATCH")
        return value

    @model_validator(mode="after")
    def _validate_rubric(self) -> Self:
        keys = [c.key for c in self.criteria]
        if len(keys) != len(set(keys)):
            raise ValueError("criterion keys must be unique")
        total = math.fsum(c.weight for c in self.criteria)
        if not math.isclose(total, 1.0, abs_tol=WEIGHT_SUM_TOLERANCE):
            raise ValueError(f"criteria weights must sum to 1.0 (got {total:.6f})")
        if self.calibration_status == "proposed_unvalidated" and not (
            self.calibration_note.strip()
        ):
            raise ValueError("proposed rubric must carry a calibration_note")
        return self

    @property
    def version_tuple(self) -> tuple[int, int, int]:
        major, minor, patch = (int(p) for p in self.rubric_version.split("."))
        return major, minor, patch


class RubricRegistry:
    """Kho rubric theo (role_key, rubric_version). Rubric đã đăng ký là bất biến."""

    def __init__(
        self,
        rubrics: Iterable[RoleRubric] = (),
        *,
        allowed_architecture_patterns: Iterable[str] = SUPPORTED_ARCHITECTURE_PATTERNS,
    ) -> None:
        self._allowed = frozenset(allowed_architecture_patterns)
        self._rubrics: dict[str, dict[str, RoleRubric]] = {}
        for rubric in rubrics:
            self.register(rubric)

    def register(self, rubric: RoleRubric) -> None:
        for criterion in rubric.criteria:
            unknown = set(criterion.patterns) - self._allowed
            if unknown:
                raise RubricConfigError(
                    f"criterion {criterion.key!r} uses architecture pattern(s) "
                    f"the system cannot provide: {sorted(unknown)}"
                )
        versions = self._rubrics.setdefault(rubric.role_key, {})
        if rubric.rubric_version in versions:
            raise RubricConfigError(
                f"rubric {rubric.role_key}@{rubric.rubric_version} already registered"
            )
        versions[rubric.rubric_version] = rubric

    def register_data(self, data: dict[str, Any]) -> RoleRubric:
        rubric = RoleRubric.model_validate(data)
        self.register(rubric)
        return rubric

    def roles(self) -> list[str]:
        return sorted(self._rubrics)

    def versions(self, role_key: str) -> list[str]:
        rubrics = self._rubrics.get(normalize_key(role_key), {})
        return [
            r.rubric_version for r in sorted(rubrics.values(), key=_version_sort_key)
        ]

    def get(self, role_key: str, version: str | None = None) -> RoleRubric:
        versions = self._rubrics.get(normalize_key(role_key))
        if not versions:
            raise RubricNotFoundError(f"no rubric registered for role {role_key!r}")
        if version is None:
            return max(versions.values(), key=_version_sort_key)
        if version not in versions:
            raise RubricNotFoundError(
                f"rubric {role_key}@{version} not found; "
                f"available: {self.versions(role_key)}"
            )
        return versions[version]

    @classmethod
    def from_directory(
        cls,
        directory: Path = DEFAULT_RUBRIC_DIR,
        **kwargs: Any,
    ) -> RubricRegistry:
        registry = cls(**kwargs)
        for path in sorted(Path(directory).glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                registry.register_data(data)
            except (OSError, ValueError) as exc:
                raise RubricConfigError(
                    f"invalid rubric file {path.name}: {exc}"
                ) from exc
        return registry


def _version_sort_key(rubric: RoleRubric) -> tuple[int, int, int]:
    return rubric.version_tuple


def load_default_registry() -> RubricRegistry:
    """Nạp các rubric đi kèm (Backend Developer, Frontend Developer)."""
    return RubricRegistry.from_directory(DEFAULT_RUBRIC_DIR)
