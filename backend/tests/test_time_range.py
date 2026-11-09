from datetime import date, datetime

import pytest
from fastapi import HTTPException

from app.core.time_range import resolve_range
from app.modules.analysis.evidence import UTC


def test_month_utc_boundary():
    start, _end = resolve_range("month", month="2026-10")
    assert start.isoformat() == "2026-10-01T00:00:00+00:00"
    assert _end.isoformat() == "2026-11-01T00:00:00+00:00"
    assert start <= datetime(2026, 10, 31, 23, 59, 59, 999999, tzinfo=UTC) < _end
    outside = _end
    assert not (start <= outside < _end)


def test_timezone_ho_chi_minh():
    start, end = resolve_range(
        "custom",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 1),
        timezone_name="Asia/Ho_Chi_Minh",
    )
    assert start.isoformat() == "2026-10-31T17:00:00+00:00"
    assert end.isoformat() == "2026-11-01T17:00:00+00:00"


def test_invalid_range():
    with pytest.raises(HTTPException):
        resolve_range(
            "custom", start_date=date(2026, 11, 2), end_date=date(2026, 11, 1)
        )


def test_invalid_month():
    with pytest.raises(HTTPException):
        resolve_range("month", month="2026-13")


def test_preset_leap_year():
    start, _end = resolve_range(
        "preset", preset="1y", now=datetime(2024, 2, 29, 12, tzinfo=UTC)
    )
    assert start.date() == date(2023, 2, 28)
