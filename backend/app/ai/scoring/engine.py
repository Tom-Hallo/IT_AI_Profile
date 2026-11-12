"""Role Scoring Engine (PBI-017) — thuần tất định, không truy cập DB/mạng/LLM.

Công thức (SRS Phụ lục B, dự thảo):
    RoleScore  = Σ(weight_i × score_i) / Σ(weight_i)   chỉ trên tiêu chí SCORED
    Coverage   = Σ(weight_i của tiêu chí SCORED) / Σ(weight_i)
Tổng điểm CHỈ được tính khi coverage ≥ ngưỡng rubric và mọi tiêu chí ``required`` đều
SCORED. Thiếu dữ liệu → UNKNOWN/INSUFFICIENT/CONFLICTING với ``score = None``, không
bao giờ gán 0. Engine không dùng commit/LOC/số repo/stars/forks làm evidence.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from statistics import fmean

from app.ai.scoring.evidence_catalog import (
    ARCHITECTURE_FINDING_TYPE,
    is_forbidden_evidence_type,
    normalize_key,
)
from app.ai.scoring.rubric import (
    METHOD_ARCH_PATTERN_COVERAGE,
    METHOD_SKILL_SCORE,
    Criterion,
    RoleRubric,
    RubricRegistry,
    load_default_registry,
)
from app.ai.scoring.schemas import (
    ConfidenceBand,
    CriterionResult,
    EvidenceExclusion,
    EvidenceRef,
    Limitation,
    RoleScoreResult,
    RoleScoringInput,
    ScoreSource,
    ScoreStatus,
    SkillScoreItem,
    SnapshotStatus,
)

Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(UTC)


def _r(value: float) -> float:
    return round(value, 2)


class _Pool:
    """Theo dõi evidence đã được tiêu chí ``evidence_exclusive`` chiếm dụng."""

    def __init__(self) -> None:
        self.claimed: dict[str, str] = {}

    def claim(self, keys: list[str], criterion_key: str) -> None:
        for key in keys:
            self.claimed.setdefault(key, criterion_key)


def _prepare_refs(
    refs: list[EvidenceRef],
    *,
    claimed: dict[str, str] | None = None,
) -> tuple[list[EvidenceRef], list[EvidenceExclusion]]:
    """Lọc: bỏ evidence bị cấm/chưa verified/trùng/đã chiếm dụng. Có thứ tự ổn định."""
    kept: dict[str, EvidenceRef] = {}
    excluded: list[EvidenceExclusion] = []
    for ref in sorted(refs, key=lambda r: (r.dedup_key, r.confidence_score)):
        key = ref.dedup_key
        if is_forbidden_evidence_type(ref.finding_type, ref.classification):
            excluded.append(
                EvidenceExclusion(evidence_key=key, reason="FORBIDDEN_TYPE")
            )
        elif not ref.verified:
            excluded.append(EvidenceExclusion(evidence_key=key, reason="UNVERIFIED"))
        elif claimed is not None and key in claimed:
            excluded.append(
                EvidenceExclusion(evidence_key=key, reason=f"CLAIMED_BY:{claimed[key]}")
            )
        elif key in kept:
            excluded.append(EvidenceExclusion(evidence_key=key, reason="DUPLICATE"))
        else:
            kept[key] = ref
    return list(kept.values()), excluded


class RoleScoringEngine:
    def __init__(
        self,
        registry: RubricRegistry | None = None,
        *,
        clock: Clock = _now,
    ) -> None:
        self.registry = registry or load_default_registry()
        self._clock = clock

    # ------------------------------------------------------------------ public API

    def score(
        self,
        data: RoleScoringInput,
        *,
        rubric_version: str | None = None,
    ) -> RoleScoreResult:
        rubric = self.registry.get(data.role_key, rubric_version)
        limitations: list[Limitation] = []
        pool = _Pool()

        snapshot = data.skill_snapshot
        snapshot_usable = snapshot is not None and snapshot.status != (
            SnapshotStatus.FAILED
        )
        if snapshot is not None and snapshot.status == SnapshotStatus.FAILED:
            limitations.append(
                Limitation(
                    code="SKILL_SNAPSHOT_FAILED",
                    message="Skill snapshot ở trạng thái FAILED nên không được dùng.",
                )
            )
        elif snapshot is not None and snapshot.status == SnapshotStatus.PARTIAL:
            limitations.append(
                Limitation(
                    code="SKILL_SNAPSHOT_PARTIAL",
                    message="Skill snapshot chưa đầy đủ; một số skill có thể thiếu.",
                )
            )

        skill_index = self._index_skills(data, snapshot_usable, limitations)
        arch_ctx = self._prepare_architecture(data, limitations)

        results: list[CriterionResult] = []
        for criterion in rubric.criteria:
            if criterion.scoring_rule.method == METHOD_SKILL_SCORE:
                result = self._score_skill(
                    criterion, skill_index, snapshot_usable, pool, limitations
                )
            elif criterion.scoring_rule.method == METHOD_ARCH_PATTERN_COVERAGE:
                result = self._score_architecture(criterion, arch_ctx, pool)
            else:  # pragma: no cover - rubric validation đã chặn
                raise ValueError(criterion.scoring_rule.method)
            results.append(result)

        self._check_scope(data, limitations)
        return self._aggregate(rubric, data, results, limitations)

    # -------------------------------------------------------------- input indexing

    def _index_skills(
        self,
        data: RoleScoringInput,
        usable: bool,
        limitations: list[Limitation],
    ) -> dict[str, list[SkillScoreItem]]:
        index: dict[str, list[SkillScoreItem]] = {}
        if not usable or data.skill_snapshot is None:
            return index
        for item in data.skill_snapshot.items:
            if is_forbidden_evidence_type(item.skill_key):
                limitations.append(
                    Limitation(
                        code="FORBIDDEN_SKILL_KEY",
                        message=(
                            f"Bỏ qua '{item.skill_key}': số liệu hoạt động "
                            "không phải bằng chứng năng lực."
                        ),
                    )
                )
                continue
            index.setdefault(item.skill_key, []).append(item)
        return index

    def _prepare_architecture(
        self,
        data: RoleScoringInput,
        limitations: list[Limitation],
    ) -> _ArchContext:
        ctx = _ArchContext()
        if data.architecture is None:
            return ctx
        ctx.provided = True
        arch_refs: list[EvidenceRef] = []
        for ref in data.architecture.evidence:
            if is_forbidden_evidence_type(ref.finding_type, ref.classification):
                limitations.append(
                    Limitation(
                        code="FORBIDDEN_EVIDENCE_TYPE",
                        message=(
                            "Bỏ qua evidence thuộc loại số liệu hoạt động "
                            f"({ref.finding_type or ref.classification})."
                        ),
                    )
                )
                continue
            if normalize_key(ref.finding_type or "") != ARCHITECTURE_FINDING_TYPE:
                continue
            if not ref.classification:
                continue
            arch_refs.append(ref)

        # Phát hiện mâu thuẫn trước khi loại trùng: cùng định danh, confidence lệch.
        groups: dict[str, list[EvidenceRef]] = {}
        for ref in arch_refs:
            groups.setdefault(ref.dedup_key, []).append(ref)
        for key, members in groups.items():
            spread = max(m.confidence_score for m in members) - min(
                m.confidence_score for m in members
            )
            ctx.spread[key] = spread
        ctx.refs = arch_refs
        return ctx

    def _check_scope(
        self, data: RoleScoringInput, limitations: list[Limitation]
    ) -> None:
        a, b = data.skill_snapshot, data.architecture
        if a is None or b is None:
            return
        pairs = (
            ("repository_scope", a.repository_scope, b.repository_scope),
            ("commit_sha", a.commit_sha, b.commit_sha),
        )
        for name, left, right in pairs:
            if left and right and left != right:
                limitations.append(
                    Limitation(
                        code="SOURCE_MISMATCH",
                        message=(
                            f"{name} của skill snapshot ({left}) khác bằng chứng "
                            f"kiến trúc ({right}); kết quả có thể không đồng nhất."
                        ),
                    )
                )

    # ------------------------------------------------------------- SKILL criteria

    def _score_skill(
        self,
        criterion: Criterion,
        index: dict[str, list[SkillScoreItem]],
        snapshot_usable: bool,
        pool: _Pool,
        limitations: list[Limitation],
    ) -> CriterionResult:
        if not snapshot_usable:
            return self._result(
                criterion,
                ScoreStatus.UNKNOWN,
                "SKILL_SNAPSHOT_UNAVAILABLE",
                "Chưa có skill snapshot hợp lệ từ PBI-016.",
            )

        claimed = pool.claimed if criterion.evidence_exclusive else None
        eligible: list[tuple[float, int, str, float, float, list[EvidenceRef]]] = []
        statuses: dict[str, tuple[ScoreStatus, str]] = {}
        excluded_all: list[EvidenceExclusion] = []

        for order, key in enumerate(criterion.skill_keys):
            items = index.get(key, [])
            if not items:
                continue
            status, reason, merged = self._merge_items(key, items, criterion)
            if status != ScoreStatus.SCORED or merged is None:
                statuses[key] = (status, reason)
                continue
            score, confidence, refs_in = merged
            refs, excluded = _prepare_refs(refs_in, claimed=claimed)
            excluded_all.extend(excluded)
            if len(refs) < criterion.minimum_evidence.min_evidence_refs:
                statuses[key] = (ScoreStatus.INSUFFICIENT, "MIN_EVIDENCE_NOT_MET")
                continue
            if confidence is None:
                statuses[key] = (ScoreStatus.INSUFFICIENT, "CONFIDENCE_MISSING")
                continue
            rule = criterion.confidence_rule
            adjusted = confidence * min(
                1.0, len(refs) / rule.evidence_for_full_confidence
            )
            if adjusted < rule.min_confidence:
                statuses[key] = (ScoreStatus.INSUFFICIENT, "LOW_CONFIDENCE")
                continue
            eligible.append((score, order, key, adjusted, confidence, refs))

        if eligible:
            # Điểm cao nhất thắng; hoà thì ưu tiên key đứng trước trong rubric.
            score, _order, key, adjusted, _raw, refs = sorted(
                eligible, key=lambda e: (-e[0], e[1])
            )[0]
            for other_key, (st, reason) in statuses.items():
                if st == ScoreStatus.CONFLICTING:
                    limitations.append(
                        Limitation(
                            code="SKILL_CONFLICT_IGNORED",
                            message=(
                                f"Skill '{other_key}' mâu thuẫn ({reason}); tiêu chí "
                                f"'{criterion.key}' dùng '{key}'."
                            ),
                        )
                    )
            if criterion.evidence_exclusive:
                pool.claim([r.dedup_key for r in refs], criterion.key)
            return self._result(
                criterion,
                ScoreStatus.SCORED,
                "SCORED",
                f"Dùng điểm skill '{key}' từ PBI-016.",
                score=_r(score),
                confidence=_r(adjusted),
                skill_key_used=key,
                evidence=refs,
                excluded=excluded_all,
            )

        if not statuses:
            return self._result(
                criterion,
                ScoreStatus.UNKNOWN,
                "NO_SKILL_ITEM",
                "Không có skill ứng viên nào trong snapshot "
                f"({', '.join(criterion.skill_keys)}).",
            )
        for wanted in (ScoreStatus.CONFLICTING, ScoreStatus.INSUFFICIENT):
            for key in criterion.skill_keys:
                if key in statuses and statuses[key][0] == wanted:
                    return self._result(
                        criterion,
                        wanted,
                        statuses[key][1],
                        f"Skill '{key}': {statuses[key][1]}.",
                        excluded=excluded_all,
                    )
        key = next(k for k in criterion.skill_keys if k in statuses)
        return self._result(
            criterion,
            ScoreStatus.UNKNOWN,
            statuses[key][1],
            f"Skill '{key}' chưa có điểm từ PBI-016.",
            excluded=excluded_all,
        )

    def _merge_items(
        self,
        key: str,
        items: list[SkillScoreItem],
        criterion: Criterion,
    ) -> tuple[ScoreStatus, str, tuple[float, float | None, list[EvidenceRef]] | None]:
        """Gộp các item cùng skill_key thành một giá trị, hoặc xác định trạng thái."""
        if any(i.status == ScoreStatus.CONFLICTING for i in items):
            return ScoreStatus.CONFLICTING, "SKILL_REPORTED_CONFLICTING", None
        scored = [i for i in items if i.status == ScoreStatus.SCORED]
        if not scored:
            if any(i.status == ScoreStatus.INSUFFICIENT for i in items):
                return ScoreStatus.INSUFFICIENT, "SKILL_REPORTED_INSUFFICIENT", None
            return ScoreStatus.UNKNOWN, "SKILL_REPORTED_UNKNOWN", None
        values = [i.score for i in scored if i.score is not None]
        if max(values) - min(values) > criterion.scoring_rule.conflict_tolerance:
            return ScoreStatus.CONFLICTING, "SKILL_SCORES_DIVERGE", None
        confidences = [i.confidence for i in scored]
        confidence = (
            None
            if any(c is None for c in confidences)
            else min(c for c in confidences if c is not None)
        )
        refs = [r for i in scored for r in i.evidence_refs]
        return ScoreStatus.SCORED, "SCORED", (fmean(values), confidence, refs)

    # ------------------------------------------------------- ARCHITECTURE criteria

    def _score_architecture(
        self,
        criterion: Criterion,
        ctx: _ArchContext,
        pool: _Pool,
    ) -> CriterionResult:
        if not ctx.provided:
            return self._result(
                criterion,
                ScoreStatus.UNKNOWN,
                "ARCHITECTURE_EVIDENCE_UNAVAILABLE",
                "Chưa có kết quả phân tích kiến trúc.",
            )
        patterns = set(criterion.patterns)
        matched = [
            r for r in ctx.refs if normalize_key(r.classification or "") in patterns
        ]
        if not matched:
            # Analyzer không phát hiện pattern ≠ bằng chứng thiếu năng lực → UNKNOWN.
            return self._result(
                criterion,
                ScoreStatus.UNKNOWN,
                "NO_MATCHING_EVIDENCE",
                "Không có evidence kiến trúc nào khớp tiêu chí này.",
            )

        tolerance = criterion.scoring_rule.conflict_tolerance
        if any(ctx.spread.get(r.dedup_key, 0.0) > tolerance for r in matched):
            return self._result(
                criterion,
                ScoreStatus.CONFLICTING,
                "ARCHITECTURE_EVIDENCE_DIVERGES",
                "Cùng một vị trí được phát hiện với confidence chênh lệch quá ngưỡng.",
            )

        claimed = pool.claimed if criterion.evidence_exclusive else None
        refs, excluded = _prepare_refs(matched, claimed=claimed)
        found = {normalize_key(r.classification or "") for r in refs}
        need = criterion.minimum_evidence
        if (
            len(refs) < need.min_evidence_refs
            or len(found) < need.min_distinct_patterns
        ):
            return self._result(
                criterion,
                ScoreStatus.INSUFFICIENT,
                "MIN_EVIDENCE_NOT_MET",
                f"Có {len(refs)} evidence / {len(found)} pattern; cần tối thiểu "
                f"{need.min_evidence_refs} / {need.min_distinct_patterns}.",
                matched_patterns=sorted(found),
                evidence=refs,
                excluded=excluded,
            )

        rule = criterion.confidence_rule
        base = fmean(r.confidence_score for r in refs) * 100.0
        adjusted = base * min(1.0, len(refs) / rule.evidence_for_full_confidence)
        if adjusted < rule.min_confidence:
            return self._result(
                criterion,
                ScoreStatus.INSUFFICIENT,
                "LOW_CONFIDENCE",
                f"Confidence {adjusted:.2f} thấp hơn ngưỡng {rule.min_confidence}.",
                matched_patterns=sorted(found),
                evidence=refs,
                excluded=excluded,
            )

        full = criterion.scoring_rule.full_score_pattern_count or 1
        score = 100.0 * min(1.0, len(found) / full)
        if criterion.evidence_exclusive:
            pool.claim([r.dedup_key for r in refs], criterion.key)
        return self._result(
            criterion,
            ScoreStatus.SCORED,
            "SCORED",
            f"Phát hiện {len(found)}/{full} pattern kiến trúc yêu cầu: "
            f"{', '.join(sorted(found))}.",
            score=_r(score),
            confidence=_r(adjusted),
            matched_patterns=sorted(found),
            evidence=refs,
            excluded=excluded,
        )

    # ----------------------------------------------------------------- aggregation

    def _result(
        self,
        criterion: Criterion,
        status: ScoreStatus,
        reason: str,
        rationale: str,
        *,
        score: float | None = None,
        confidence: float | None = None,
        skill_key_used: str | None = None,
        matched_patterns: list[str] | None = None,
        evidence: list[EvidenceRef] | None = None,
        excluded: list[EvidenceExclusion] | None = None,
    ) -> CriterionResult:
        return CriterionResult(
            key=criterion.key,
            name=criterion.name,
            type=criterion.type,
            weight=criterion.weight,
            required=criterion.required,
            status=status,
            score=score if status == ScoreStatus.SCORED else None,
            confidence=confidence if status == ScoreStatus.SCORED else None,
            reason_code=reason,
            rationale=rationale,
            skill_key_used=skill_key_used,
            matched_patterns=matched_patterns or [],
            evidence_refs=evidence or [],
            excluded_evidence=excluded or [],
        )

    def _aggregate(
        self,
        rubric: RoleRubric,
        data: RoleScoringInput,
        results: list[CriterionResult],
        limitations: list[Limitation],
    ) -> RoleScoreResult:
        total_w = math.fsum(c.weight for c in results)
        scored = [c for c in results if c.status == ScoreStatus.SCORED]
        scored_w = math.fsum(c.weight for c in scored)
        coverage = scored_w / total_w if total_w else 0.0
        required_unmet = [
            c.key for c in results if c.required and c.status != ScoreStatus.SCORED
        ]
        non_scored = [c for c in results if c.status != ScoreStatus.SCORED]
        min_cov = rubric.thresholds.min_coverage

        role_score: float | None = None
        confidence: float | None = None
        if all(c.status == ScoreStatus.UNKNOWN for c in results):
            status, reason = ScoreStatus.UNKNOWN, "NO_DATA"
            rationale = "Không có dữ liệu nào cho các tiêu chí của role."
        elif coverage + 1e-9 < min_cov or required_unmet:
            blockers = [
                c for c in non_scored if c.key in required_unmet or coverage < min_cov
            ]
            if any(c.status == ScoreStatus.CONFLICTING for c in blockers):
                status, reason = ScoreStatus.CONFLICTING, "CONFLICTING_EVIDENCE"
            else:
                status, reason = (
                    ScoreStatus.INSUFFICIENT,
                    ("REQUIRED_CRITERIA_UNMET" if required_unmet else "LOW_COVERAGE"),
                )
            rationale = (
                f"Coverage {coverage:.2f} (ngưỡng {min_cov:.2f}); tiêu chí bắt buộc "
                f"chưa đạt: {', '.join(required_unmet) or 'không'}. "
                "Không tính tổng điểm."
            )
        else:
            status, reason = ScoreStatus.SCORED, "SCORED"
            role_score = _r(
                math.fsum(c.weight * (c.score or 0.0) for c in scored) / scored_w
            )
            confidence = _r(
                math.fsum(c.weight * (c.confidence or 0.0) for c in scored)
                / scored_w
                * coverage
            )
            rationale = (
                f"Chấm {len(scored)}/{len(results)} tiêu chí, coverage {coverage:.2f}."
            )
            for c in non_scored:
                limitations.append(
                    Limitation(
                        code=f"CRITERION_{c.status.value}",
                        message=f"Tiêu chí '{c.key}' {c.status.value} "
                        f"({c.reason_code}); "
                        "không tính vào điểm.",
                    )
                )

        band = ConfidenceBand.NONE
        if confidence is not None:
            if confidence >= rubric.thresholds.confidence_high:
                band = ConfidenceBand.HIGH
            elif confidence >= rubric.thresholds.confidence_medium:
                band = ConfidenceBand.MEDIUM
            else:
                band = ConfidenceBand.LOW

        used: dict[str, EvidenceRef] = {}
        for c in results:
            for ref in c.evidence_refs:
                used.setdefault(ref.dedup_key, ref)

        snap, arch = data.skill_snapshot, data.architecture
        return RoleScoreResult(
            role_key=rubric.role_key,
            rubric_version=rubric.rubric_version,
            status=status,
            role_score=role_score,
            coverage=_r(coverage),
            confidence=confidence,
            confidence_band=band,
            reason_code=reason,
            rationale=rationale,
            required_unmet=required_unmet,
            source=ScoreSource(
                skill_snapshot_ref=snap.snapshot_ref if snap else None,
                skill_snapshot_status=snap.status if snap else None,
                skill_context=snap.model_copy(update={"items": []}, deep=True)
                if snap
                else None,
                architecture_context=arch.model_copy(update={"evidence": []}, deep=True)
                if arch
                else None,
            ),
            criteria=results,
            evidence_refs=[used[k] for k in sorted(used)],
            limitations=limitations,
            scored_at=self._clock(),
        )


class _ArchContext:
    def __init__(self) -> None:
        self.provided = False
        self.refs: list[EvidenceRef] = []
        self.spread: dict[str, float] = {}
