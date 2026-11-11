import pytest

from app.modules.scoring.engine import WEIGHTS, Metric, calculate


def full(value):
    return {name: Metric(value, (i + 1,)) for i, name in enumerate(WEIGHTS)}


def test_maximum():
    assert calculate(full(1))["score"] == 100


def test_minimum_with_real_evidence():
    result = calculate(full(0))
    assert result["score"] == 0 and result["status"] == "Scored"


def test_missing_is_not_zero():
    metrics = full(1)
    metrics["complexity"] = Metric(None)
    result = calculate(metrics)
    assert result["score"] is None and result["status"] == "Insufficient"


def test_missing_link_is_insufficient():
    metrics = full(1)
    metrics["confidence"] = Metric(1)
    assert calculate(metrics)["score"] is None


def test_weighted_score():
    metrics = full(0)
    metrics["code_contribution"] = Metric(1, (1,))
    assert calculate(metrics)["score"] == 30


def test_invalid_normalization():
    with pytest.raises(ValueError):
        calculate(full(1.1))


def test_version_is_returned():
    assert calculate(full(0.5), rubric_version="2.0.0")["rubric_version"] == "2.0.0"
