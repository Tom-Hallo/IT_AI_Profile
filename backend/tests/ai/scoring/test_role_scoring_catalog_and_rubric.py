import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ai.scoring import (
    RoleRubric,
    RubricConfigError,
    RubricNotFoundError,
    RubricRegistry,
    load_default_registry,
)
from app.ai.scoring.evidence_catalog import (
    FORBIDDEN_EVIDENCE_TYPES,
    SUPPORTED_ARCHITECTURE_PATTERNS,
    is_forbidden_evidence_type,
)
from app.ai.scoring.rubric import DEFAULT_RUBRIC_DIR

ARCHITECTURE_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "modules"
    / "analysis"
    / "architecture.py"
)


def _skill_criterion(key="c1", weight=1.0, **over):
    data = {
        "key": key,
        "name": "n",
        "description": "d",
        "type": "SKILL",
        "source_skill_key": "python",
        "weight": weight,
        "scoring_rule": {"method": "skill_score"},
    }
    data.update(over)
    return data


def _rubric(criteria, **over):
    data = {
        "role_key": "test_role",
        "rubric_version": "1.0.0",
        "name": "Test",
        "calibration_note": "proposed",
        "thresholds": {"min_coverage": 0.5},
        "criteria": criteria,
    }
    data.update(over)
    return data


# ---------------------------------------------------------------- catalog


def test_architecture_catalog_matches_analyzer_source():
    source = ARCHITECTURE_SOURCE.read_text(encoding="utf-8")
    for pattern in SUPPORTED_ARCHITECTURE_PATTERNS:
        assert f'classification="{pattern}"' in source, pattern


def test_forbidden_metrics_detected():
    for name in ("commit_count", "Lines of Code", "stars", "forks", "repo_count"):
        assert is_forbidden_evidence_type(name)
    assert not is_forbidden_evidence_type("architecture", "api_service")
    assert {"stars", "forks", "commit_count", "lines_of_code"} <= (
        FORBIDDEN_EVIDENCE_TYPES
    )


# ----------------------------------------------------------- default rubrics


@pytest.mark.parametrize("role", ["backend_developer", "frontend_developer"])
def test_default_rubrics_valid(role):
    rubric = load_default_registry().get(role)
    assert sum(c.weight for c in rubric.criteria) == pytest.approx(1.0)
    assert rubric.rubric_version == "1.0.0"
    assert rubric.calibration_status == "proposed_unvalidated"
    assert rubric.calibration_note
    for c in rubric.criteria:
        assert c.name and c.description
        assert c.type.value in {"SKILL", "ARCHITECTURE"}
        assert (c.type.value == "SKILL") == bool(c.source_skill_key)
        assert c.scoring_rule.method
        assert c.minimum_evidence.min_evidence_refs >= 1


def test_rubric_files_load_from_directory():
    files = sorted(DEFAULT_RUBRIC_DIR.glob("*.json"))
    assert len(files) >= 2
    for f in files:
        RoleRubric.model_validate(json.loads(f.read_text(encoding="utf-8")))


# ----------------------------------------------------- invalid configuration


def test_weights_must_sum_to_one():
    with pytest.raises(ValidationError, match="sum to 1.0"):
        RoleRubric.model_validate(
            _rubric([_skill_criterion("a", 0.5), _skill_criterion("b", 0.4)])
        )


@pytest.mark.parametrize("weight", [0, -0.1, 1.5])
def test_weight_out_of_range_rejected(weight):
    with pytest.raises(ValidationError):
        RoleRubric.model_validate(_rubric([_skill_criterion("a", weight)]))


def test_duplicate_criterion_keys_rejected():
    with pytest.raises(ValidationError, match="unique"):
        RoleRubric.model_validate(
            _rubric([_skill_criterion("a", 0.5), _skill_criterion("a", 0.5)])
        )


def test_skill_criterion_requires_source_skill_key():
    with pytest.raises(ValidationError, match="source_skill_key"):
        RoleRubric.model_validate(
            _rubric([_skill_criterion("a", 1.0, source_skill_key=None)])
        )


def test_method_must_match_type():
    bad = _skill_criterion(
        "a", 1.0, scoring_rule={"method": "architecture_pattern_coverage"}
    )
    with pytest.raises(ValidationError, match="not valid for type"):
        RoleRubric.model_validate(_rubric([bad]))


def test_unknown_method_rejected():
    bad = _skill_criterion("a", 1.0, scoring_rule={"method": "magic"})
    with pytest.raises(ValidationError, match="unknown scoring method"):
        RoleRubric.model_validate(_rubric([bad]))


def test_version_format_and_calibration_note_required():
    with pytest.raises(ValidationError):
        RoleRubric.model_validate(_rubric([_skill_criterion()], rubric_version="v1"))
    with pytest.raises(ValidationError, match="calibration_note"):
        RoleRubric.model_validate(_rubric([_skill_criterion()], calibration_note=""))


def test_unsupported_architecture_pattern_rejected_unless_extended():
    arch = {
        "key": "x",
        "name": "n",
        "description": "d",
        "type": "ARCHITECTURE",
        "architecture_patterns": ["microservices_mesh"],
        "weight": 1.0,
        "scoring_rule": {
            "method": "architecture_pattern_coverage",
            "full_score_pattern_count": 1,
        },
    }
    rubric = RoleRubric.model_validate(_rubric([arch]))
    with pytest.raises(RubricConfigError, match="cannot provide"):
        RubricRegistry().register(rubric)
    registry = RubricRegistry(
        allowed_architecture_patterns={"microservices_mesh"},
    )
    registry.register(rubric)
    assert registry.roles() == ["test_role"]


def test_registry_duplicate_and_not_found():
    registry = RubricRegistry()
    registry.register_data(_rubric([_skill_criterion()]))
    with pytest.raises(RubricConfigError, match="already registered"):
        registry.register_data(_rubric([_skill_criterion()]))
    with pytest.raises(RubricNotFoundError):
        registry.get("missing")
    with pytest.raises(RubricNotFoundError):
        registry.get("test_role", "9.9.9")


def test_invalid_rubric_file_reports_filename(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RubricConfigError, match="broken.json"):
        RubricRegistry.from_directory(tmp_path)
