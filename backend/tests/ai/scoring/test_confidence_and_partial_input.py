"""Confidence band, input không đầy đủ và tính tất định (PBI-017)."""

from __future__ import annotations

import pytest

from app.ai.scoring import (
    ConfidenceBand,
    RoleScoringEngine,
    RoleScoringInput,
    ScoreStatus,
    SnapshotStatus,
)
from tests.ai.scoring.conftest import (
    FIXED_NOW,
    arch_ref,
    arch_set,
    backend_full,
    skill,
    snapshot,
)


@pytest.fixture
def engine() -> RoleScoringEngine:
    return RoleScoringEngine(clock=lambda: FIXED_NOW)


def _backend(skill_conf: float, arch_conf: float) -> RoleScoringInput:
    return RoleScoringInput(
        role_key="backend_developer",
        skill_snapshot=snapshot(
            [
                skill("python", 80, confidence=skill_conf),
                skill("fastapi", 80, confidence=skill_conf),
                skill("sqlalchemy", 80, confidence=skill_conf),
            ]
        ),
        architecture=arch_set(
            [
                arch_ref(
                    "api_service", "backend/app/api/router.py", confidence=arch_conf
                ),
                arch_ref(
                    "layered_architecture", "backend/app/s.py", confidence=arch_conf
                ),
                arch_ref(
                    "database_integration", "backend/alembic.ini", confidence=arch_conf
                ),
                arch_ref(
                    "background_workers", "backend/app/w.py", confidence=arch_conf
                ),
            ]
        ),
    )


@pytest.mark.parametrize(
    ("skill_conf", "arch_conf", "band"),
    [
        (95, 0.95, ConfidenceBand.HIGH),
        (60, 0.60, ConfidenceBand.MEDIUM),
        (40, 0.50, ConfidenceBand.LOW),  # đúng ngưỡng tối thiểu của từng tiêu chí
    ],
)
def test_confidence_band_follows_rubric_thresholds(engine, skill_conf, arch_conf, band):
    result = engine.score(_backend(skill_conf, arch_conf))
    assert result.status == ScoreStatus.SCORED
    assert result.confidence_band == band


def test_confidence_is_none_when_not_scored(engine):
    result = engine.score(RoleScoringInput(role_key="backend_developer"))
    assert result.confidence is None
    assert result.confidence_band == ConfidenceBand.NONE


def test_confidence_scales_down_with_coverage(engine):
    full = engine.score(backend_full())
    partial_input = backend_full()
    partial_input.architecture.evidence = [
        r
        for r in partial_input.architecture.evidence
        if r.classification != "background_workers"
    ]
    partial = engine.score(partial_input)
    assert partial.status == ScoreStatus.SCORED
    assert partial.coverage < full.coverage
    assert partial.confidence < full.confidence


@pytest.mark.parametrize("drop", ["skill_snapshot", "architecture"])
def test_missing_one_source_never_yields_total_score_of_zero(engine, drop):
    data = backend_full()
    setattr(data, drop, None)
    result = engine.score(data)
    assert result.role_score != 0
    unknown = [c for c in result.criteria if c.status == ScoreStatus.UNKNOWN]
    assert unknown
    assert all(c.score is None for c in unknown)


def test_partial_snapshot_is_reported_but_still_used(engine):
    data = backend_full()
    data.skill_snapshot.status = SnapshotStatus.PARTIAL
    result = engine.score(data)
    assert any(lim.code == "SKILL_SNAPSHOT_PARTIAL" for lim in result.limitations)
    assert result.criterion("backend_language").status == ScoreStatus.SCORED


def test_empty_snapshot_items_gives_unknown_skills(engine):
    data = backend_full()
    data.skill_snapshot.items = []
    result = engine.score(data)
    for key in ("backend_language", "backend_framework", "orm_data_access"):
        assert result.criterion(key).status == ScoreStatus.UNKNOWN
    assert result.role_score is None


def test_determinism_across_instances_and_repeats(engine):
    runs = [
        RoleScoringEngine(clock=lambda: FIXED_NOW)
        .score(backend_full())
        .model_dump_json()
        for _ in range(5)
    ]
    runs.append(engine.score(backend_full()).model_dump_json())
    assert len(set(runs)) == 1


def test_scoring_does_not_mutate_input(engine):
    data = backend_full()
    before = data.model_dump_json()
    engine.score(data)
    assert data.model_dump_json() == before
