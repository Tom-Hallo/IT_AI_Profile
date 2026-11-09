from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException

UTC = timezone.utc

def resolve_range(mode: str, preset: str | None = None, month: str | None = None,
                  start_date: date | None = None, end_date: date | None = None,
                  timezone_name: str = 'UTC', now: datetime | None = None):
    try:
        tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, 'Invalid IANA timezone')
    now = (now or datetime.now(UTC)).astimezone(tz)
    if mode == 'preset':
        if preset not in ('1m', '3m', '6m', '1y') or any(v is not None for v in (month, start_date, end_date)):
            raise HTTPException(422, 'Invalid preset parameters')
        # Rolling calendar months, anchored to the current local date/time.
        months = {'1m': 1, '3m': 3, '6m': 6, '1y': 12}[preset]
        y, m = now.year, now.month - months
        while m <= 0:
            y -= 1
            m += 12
        d = min(now.day, monthrange(y, m)[1])
        lower = now.replace(year=y, month=m, day=d)
        upper = now
    elif mode == 'month':
        if month is None or any(v is not None for v in (preset, start_date, end_date)):
            raise HTTPException(422, 'Invalid month parameters')
        import re
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
            raise HTTPException(422, 'month must be YYYY-MM')
        y, m = map(int, month.split('-'))
        if y < 1:
            raise HTTPException(422, 'Invalid year')
        lower = datetime(y, m, 1, tzinfo=tz)
        upper = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=tz)
    elif mode == 'custom':
        if not start_date or not end_date or preset is not None or month is not None:
            raise HTTPException(422, 'Invalid custom parameters')
        if start_date > end_date or (end_date - start_date).days > 3660:
            raise HTTPException(422, 'Invalid date range (max 3660 days)')
        lower = datetime.combine(start_date, time.min, tz)
        upper = datetime.combine(end_date + timedelta(days=1), time.min, tz)
    else:
        raise HTTPException(422, 'Invalid mode')
    return lower.astimezone(UTC), upper.astimezone(UTC)
