import pytest

from app.ai.scoring import (
    EvidenceRef,
    RoleScoringEngine,
    RoleScoringInput,
    RubricNotFoundError,
    RubricRegistry,
    ScoreStatus,
    SkillScoreItem,
    SnapshotStatus,
    load_default_registry,
)
from tests.ai.scoring.conftest import (  # noqa: I001
    FIXED_NOW,
    arch_ref,
    arch_set,
    backend_full,
    frontend_full,
    skill,
    snapshot,
)


def _custom_rubric(version="1.0.0", weights=(0.5, 0.5), min_coverage=0.5, **over):
    data = {
        "role_key": "custom_role",
        "rubric_version": version,
        "name": "Custom",
        "calibration_note": "proposed",
        "thresholds": {"min_coverage": min_coverage},
        "criteria": [
            {
                "key": "k_python",
                "name": "py",
                "description": "d",
                "type": "SKILL",
                "source_skill_key": "python",
                "weight": weights[0],
                "required": False,
                "scoring_rule": {"method": "skill_score", "conflict_tolerance": 10},
                "minimum_evidence": {"min_evidence_refs": 1},
                "confidence_rule": {"min_confidence": 30},
            },
            {
                "key": "k_workers",
                "name": "workers",
                "description": "d",
                "type": "ARCHITECTURE",
                "architecture_patterns": ["background_workers"],
                "weight": weights[1],
                "required": False,
                "scoring_rule": {
                    "method": "architecture_pattern_coverage",
                    "full_score_pattern_count": 1,
                },
            },
        ],
    }
    data.update(over)
    return data


# ------------------------------------------------------------ valid input


def test_backend_full_score(engine):
    result = engine.score(backend_full())
    assert result.status == ScoreStatus.SCORED
    assert result.role_score == 86.0
    assert result.coverage == 1.0
    assert result.confidence == 79.0
    assert result.confidence_band.value == "HIGH"
    assert result.rubric_version == "1.0.0"
    assert result.scored_at == FIXED_NOW
    assert result.source.skill_snapshot_ref == "snap-1"
    assert result.source.skill_context.report_ref == "report-9"
    assert result.source.architecture_context.repository_scope == "combined"
    assert all(c.status == ScoreStatus.SCORED for c in result.criteria)
    assert result.criterion("backend_framework").skill_key_used == "fastapi"


def test_frontend_full_score(engine):
    result = engine.score(frontend_full())
    assert result.status == ScoreStatus.SCORED
    # .30*90 + .35*80 + .15*50 + .20*100 = 27 + 28 + 7.5 + 20
    assert result.role_score == 82.5
    assert result.coverage == 1.0
    assert result.role_key == "frontend_developer"


def test_evidence_traceable_per_criterion_and_role(engine):
    result = engine.score(backend_full())
    api = result.criterion("api_service_design")
    assert [r.file_path for r in api.evidence_refs] == ["backend/app/api/router.py"]
    assert api.matched_patterns == ["api_service"]
    paths = {r.file_path for r in result.evidence_refs}
    assert "backend/alembic.ini" in paths and "src/python_0" in paths
    keys = [r.dedup_key for r in result.evidence_refs]
    assert len(keys) == len(set(keys))


def test_best_of_alternative_skill_keys(engine):
    data = backend_full()
    items = [*data.skill_snapshot.items, skill("java", 95, confidence=70)]
    data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(update={"items": items})
        }
    )
    result = engine.score(data)
    crit = result.criterion("backend_language")
    assert crit.skill_key_used == "java" and crit.score == 95.0


def test_skill_keys_are_normalized(engine):
    data = frontend_full()
    items = [skill("Next.js", 99, confidence=90), *data.skill_snapshot.items]
    data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(update={"items": items})
        }
    )
    assert (
        engine.score(data).criterion("frontend_framework").skill_key_used == "next_js"
    )


# ------------------------------------------------------ missing data / UNKNOWN


def test_no_input_is_unknown_not_zero(engine):
    result = engine.score(RoleScoringInput(role_key="backend_developer"))
    assert result.status == ScoreStatus.UNKNOWN
    assert result.role_score is None and result.confidence is None
    assert result.coverage == 0.0
    for c in result.criteria:
        assert c.status == ScoreStatus.UNKNOWN
        assert c.score is None  # tuyệt đối không phải 0


def test_failed_snapshot_ignored(engine):
    data = backend_full()
    data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(
                update={"status": SnapshotStatus.FAILED}
            )
        }
    )
    result = engine.score(data)
    assert result.criterion("backend_language").reason_code == (
        "SKILL_SNAPSHOT_UNAVAILABLE"
    )
    assert result.status == ScoreStatus.INSUFFICIENT
    assert any(lim.code == "SKILL_SNAPSHOT_FAILED" for lim in result.limitations)


def test_only_architecture_evidence_gives_insufficient_without_total(engine):
    data = backend_full().model_copy(update={"skill_snapshot": None})
    result = engine.score(data)
    assert result.status == ScoreStatus.INSUFFICIENT
    assert result.role_score is None
    assert result.coverage == 0.5
    assert "backend_language" in result.required_unmet
    assert result.criterion("api_service_design").score == 100.0  # vẫn chấm riêng


def test_absent_architecture_pattern_is_unknown_not_zero(engine):
    data = backend_full()
    data = data.model_copy(
        update={"architecture": arch_set([arch_ref("monorepo", "docker-compose.yml")])}
    )
    crit = engine.score(data).criterion("api_service_design")
    assert crit.status == ScoreStatus.UNKNOWN and crit.score is None


def test_skill_reported_unknown_status(engine):
    data = backend_full()
    items = [skill("python", None, confidence=None, status="unknown")]
    items += [i for i in data.skill_snapshot.items if i.skill_key != "python"]
    data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(update={"items": items})
        }
    )
    result = engine.score(data)
    crit = result.criterion("backend_language")
    assert crit.status == ScoreStatus.UNKNOWN and crit.score is None
    assert result.status == ScoreStatus.INSUFFICIENT  # required thiếu


# ------------------------------------------------------------- INSUFFICIENT


def test_insufficient_min_evidence(engine):
    data = backend_full()
    items = [skill("python", 80, refs=0)]
    items += [i for i in data.skill_snapshot.items if i.skill_key != "python"]
    data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(update={"items": items})
        }
    )
    crit = engine.score(data).criterion("backend_language")
    assert crit.status == ScoreStatus.INSUFFICIENT
    assert crit.reason_code == "MIN_EVIDENCE_NOT_MET" and crit.score is None


def test_insufficient_low_confidence_and_missing_confidence(engine):
    data = backend_full()
    for conf, reason in ((10, "LOW_CONFIDENCE"), (None, "CONFIDENCE_MISSING")):
        items = [skill("python", 80, confidence=conf)]
        items += [i for i in data.skill_snapshot.items if i.skill_key != "python"]
        d = data.model_copy(
            update={
                "skill_snapshot": data.skill_snapshot.model_copy(
                    update={"items": items}
                )
            }
        )
        crit = engine.score(d).criterion("backend_language")
        assert (crit.status, crit.reason_code) == (ScoreStatus.INSUFFICIENT, reason)


def test_insufficient_architecture_low_confidence(engine):
    data = backend_full()
    data = data.model_copy(
        update={"architecture": arch_set([arch_ref("api_service", confidence=0.2)])}
    )
    crit = engine.score(data).criterion("api_service_design")
    assert crit.status == ScoreStatus.INSUFFICIENT and crit.reason_code == (
        "LOW_CONFIDENCE"
    )


# ------------------------------------------------------------- CONFLICTING


def test_conflicting_diverging_skill_scores(engine):
    data = backend_full()
    items = [skill("python", 90, ref_prefix="p1"), skill("python", 30, ref_prefix="p2")]
    items += [i for i in data.skill_snapshot.items if i.skill_key != "python"]
    data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(update={"items": items})
        }
    )
    result = engine.score(data)
    crit = result.criterion("backend_language")
    assert crit.status == ScoreStatus.CONFLICTING and crit.score is None
    assert result.status == ScoreStatus.CONFLICTING  # required bị chặn
    assert result.role_score is None


def test_close_duplicate_skill_items_are_merged(engine):
    data = backend_full()
    items = [skill("python", 80, ref_prefix="p1"), skill("python", 84, ref_prefix="p2")]
    items += [i for i in data.skill_snapshot.items if i.skill_key != "python"]
    data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(update={"items": items})
        }
    )
    crit = engine.score(data).criterion("backend_language")
    assert crit.status == ScoreStatus.SCORED and crit.score == 82.0
    assert len(crit.evidence_refs) == 2


def test_conflicting_reported_by_skill_source(engine):
    data = backend_full()
    items = [skill("fastapi", None, confidence=None, status="CONFLICTING")]
    items += [i for i in data.skill_snapshot.items if i.skill_key != "fastapi"]
    data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(update={"items": items})
        }
    )
    assert (
        engine.score(data).criterion("backend_framework").status
        == ScoreStatus.CONFLICTING
    )


def test_conflicting_architecture_detector_disagreement(engine):
    data = backend_full()
    data = data.model_copy(
        update={
            "architecture": arch_set(
                [
                    arch_ref("api_service", "backend/api/r.py", confidence=0.95),
                    arch_ref("api_service", "backend/api/r.py", confidence=0.30),
                ]
            )
        }
    )
    assert (
        engine.score(data).criterion("api_service_design").status
        == ScoreStatus.CONFLICTING
    )


def test_conflicting_optional_criterion_excluded_but_reported(engine):
    data = backend_full()
    items = [
        skill("sqlalchemy", 90, ref_prefix="a"),
        skill("sqlalchemy", 10, ref_prefix="b"),
    ]
    items += [i for i in data.skill_snapshot.items if i.skill_key != "sqlalchemy"]
    data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(update={"items": items})
        }
    )
    result = engine.score(data)
    assert result.criterion("orm_data_access").status == ScoreStatus.CONFLICTING
    assert result.status == ScoreStatus.SCORED  # coverage 0.9, required đủ
    assert result.coverage == 0.9
    assert any(lim.code == "CRITERION_CONFLICTING" for lim in result.limitations)


# ---------------------------------------------------------------- coverage


def test_low_coverage_blocks_total_when_no_required_criteria():
    registry = RubricRegistry()
    registry.register_data(_custom_rubric(min_coverage=0.8))
    engine = RoleScoringEngine(registry, clock=lambda: FIXED_NOW)
    data = RoleScoringInput(
        role_key="custom_role", skill_snapshot=snapshot([skill("python", 70)])
    )
    result = engine.score(data)
    assert result.coverage == 0.5
    assert result.status == ScoreStatus.INSUFFICIENT
    assert result.reason_code == "LOW_COVERAGE"
    assert result.role_score is None and result.confidence is None


def test_coverage_at_threshold_scores_and_normalizes_by_scored_weight():
    registry = RubricRegistry()
    registry.register_data(_custom_rubric(min_coverage=0.5))
    engine = RoleScoringEngine(registry, clock=lambda: FIXED_NOW)
    data = RoleScoringInput(
        role_key="custom_role", skill_snapshot=snapshot([skill("python", 70)])
    )
    result = engine.score(data)
    assert result.status == ScoreStatus.SCORED
    assert result.role_score == 70.0  # chia cho tổng trọng số đã chấm
    assert result.confidence == 40.0  # 80 * coverage 0.5
    assert result.confidence_band.value == "LOW"


# ---------------------------------------------------------------- evidence


def test_duplicate_evidence_counted_once(engine):
    data = backend_full()
    dup = arch_ref("api_service", "backend/app/api/router.py")
    data = data.model_copy(
        update={
            "architecture": arch_set(
                [dup, dup, arch_ref("api_service", "backend/app/api/router.py")]
            )
        }
    )
    crit = engine.score(data).criterion("api_service_design")
    assert len(crit.evidence_refs) == 1
    assert any(e.reason == "DUPLICATE" for e in crit.excluded_evidence)


def test_exclusive_evidence_not_reused_across_criteria():
    registry = RubricRegistry()
    data = _custom_rubric()
    data["criteria"] = [
        {
            "key": "first",
            "name": "a",
            "description": "d",
            "type": "ARCHITECTURE",
            "architecture_patterns": ["api_service"],
            "weight": 0.5,
            "required": False,
            "evidence_exclusive": True,
            "scoring_rule": {
                "method": "architecture_pattern_coverage",
                "full_score_pattern_count": 1,
            },
        },
        {
            "key": "second",
            "name": "b",
            "description": "d",
            "type": "ARCHITECTURE",
            "architecture_patterns": ["api_service", "layered_architecture"],
            "weight": 0.5,
            "required": False,
            "evidence_exclusive": True,
            "scoring_rule": {
                "method": "architecture_pattern_coverage",
                "full_score_pattern_count": 1,
            },
        },
    ]
    registry.register_data(data)
    engine = RoleScoringEngine(registry, clock=lambda: FIXED_NOW)
    shared = arch_ref("api_service", "backend/api/router.py")
    result = engine.score(
        RoleScoringInput(role_key="custom_role", architecture=arch_set([shared]))
    )
    assert result.criterion("first").status == ScoreStatus.SCORED
    second = result.criterion("second")
    assert second.status == ScoreStatus.INSUFFICIENT
    assert any(e.reason == "CLAIMED_BY:first" for e in second.excluded_evidence)
    assert len(result.evidence_refs) == 1


def test_forbidden_activity_metrics_never_used_as_evidence(engine):
    data = backend_full()
    bad = [
        EvidenceRef(
            evidence_id="c1", finding_type="commit_count", classification="api_service"
        ),
        EvidenceRef(
            evidence_id="s1", finding_type="architecture", classification="stars"
        ),
        EvidenceRef(
            evidence_id="f1", finding_type="forks", classification="api_service"
        ),
    ]
    data = data.model_copy(update={"architecture": arch_set(bad)})
    result = engine.score(data)
    assert result.criterion("api_service_design").status == ScoreStatus.UNKNOWN
    assert any(lim.code == "FORBIDDEN_EVIDENCE_TYPE" for lim in result.limitations)
    items = [
        *backend_full().skill_snapshot.items,
        SkillScoreItem(skill_key="stars", score=100, confidence=100),
    ]
    data2 = backend_full().model_copy(update={"skill_snapshot": snapshot(items)})
    assert any(
        lim.code == "FORBIDDEN_SKILL_KEY" for lim in engine.score(data2).limitations
    )


def test_unverified_evidence_excluded(engine):
    data = backend_full()
    data = data.model_copy(
        update={"architecture": arch_set([arch_ref("api_service", verified=False)])}
    )
    crit = engine.score(data).criterion("api_service_design")
    assert crit.status == ScoreStatus.INSUFFICIENT
    assert any(e.reason == "UNVERIFIED" for e in crit.excluded_evidence)


def test_source_mismatch_reported(engine):
    data = backend_full()
    data = data.model_copy(
        update={
            "architecture": data.architecture.model_copy(
                update={"repository_scope": "public"}
            )
        }
    )
    assert any(lim.code == "SOURCE_MISMATCH" for lim in engine.score(data).limitations)


# ------------------------------------------------------------ determinism


def test_same_input_same_output(engine):
    first = engine.score(backend_full()).model_dump()
    second = engine.score(backend_full()).model_dump()
    assert first == second


def test_input_order_does_not_change_result(engine):
    data = backend_full()
    reversed_data = data.model_copy(
        update={
            "skill_snapshot": data.skill_snapshot.model_copy(
                update={"items": list(reversed(data.skill_snapshot.items))}
            ),
            "architecture": data.architecture.model_copy(
                update={"evidence": list(reversed(data.architecture.evidence))}
            ),
        }
    )
    a = engine.score(data).model_dump()
    b = engine.score(reversed_data).model_dump()
    assert a == b


# ------------------------------------------------------ versions / new roles


def test_rubric_versions_select_and_change_result():
    registry = RubricRegistry()
    registry.register_data(_custom_rubric("1.0.0", weights=(0.5, 0.5)))
    registry.register_data(_custom_rubric("1.1.0", weights=(0.8, 0.2)))
    engine = RoleScoringEngine(registry, clock=lambda: FIXED_NOW)
    data = RoleScoringInput(
        role_key="custom_role",
        skill_snapshot=snapshot([skill("python", 50)]),
        architecture=arch_set([arch_ref("background_workers")]),
    )
    v1 = engine.score(data, rubric_version="1.0.0")
    latest = engine.score(data)
    assert registry.versions("custom_role") == ["1.0.0", "1.1.0"]
    assert (v1.rubric_version, v1.role_score) == ("1.0.0", 75.0)
    assert (latest.rubric_version, latest.role_score) == ("1.1.0", 60.0)
    with pytest.raises(RubricNotFoundError):
        engine.score(data, rubric_version="2.0.0")


def test_new_role_added_by_configuration_only():
    registry = load_default_registry()
    registry.register_data(_custom_rubric())
    assert "custom_role" in registry.roles()
    engine = RoleScoringEngine(registry, clock=lambda: FIXED_NOW)
    data = RoleScoringInput(
        role_key="Custom Role",
        skill_snapshot=snapshot([skill("python", 90)]),
        architecture=arch_set([arch_ref("background_workers")]),
    )
    result = engine.score(data)
    assert result.status == ScoreStatus.SCORED and result.role_score == 95.0


def test_unknown_role_raises():
    engine = RoleScoringEngine(load_default_registry())
    with pytest.raises(RubricNotFoundError):
        engine.score(RoleScoringInput(role_key="data_scientist"))


# ------------------------------------------------------------------- DTO


def test_dto_validation():
    with pytest.raises(ValueError, match="requires a score"):
        SkillScoreItem(skill_key="python", status="SCORED", score=None)
    with pytest.raises(ValueError):
        SkillScoreItem(skill_key="python", score=120)
    with pytest.raises(ValueError, match="evidence_id or file_path"):
        EvidenceRef(finding_type="architecture")


def test_evidence_ref_from_analysis_record():
    from app.modules.analysis.evidence import (
        DetectionMethod,
        EvidenceRecord,
        EvidenceSource,
        FindingType,
    )

    record = EvidenceRecord(
        repository_id=7,
        commit_sha="b" * 40,
        file_path="backend/app/api/router.py",
        finding_type=FindingType.ARCHITECTURE,
        classification="api_service",
        evidence_source=EvidenceSource.SOURCE_CODE,
        detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
        rationale="r",
        confidence_score=0.9,
    )
    ref = EvidenceRef.from_record(record, evidence_id=42)
    assert (ref.evidence_id, ref.finding_type, ref.classification) == (
        "42",
        "architecture",
        "api_service",
    )
    assert ref.repository_id == 7 and ref.confidence_score == 0.9
