from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo


def parse_day(value: Optional[str], timezone_name: str = "Asia/Shanghai") -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now(ZoneInfo(timezone_name)).date()


def local_day_to_utc_range(day: date, timezone_name: str = "Asia/Shanghai") -> Tuple[datetime, datetime]:
    local_tz = ZoneInfo(timezone_name)
    start_local = datetime.combine(day, time.min, tzinfo=local_tz)
    end_local = start_local + timedelta(days=1) - timedelta(minutes=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def arxiv_date_range(day: date, timezone_name: str = "Asia/Shanghai") -> str:
    start_utc, end_utc = local_day_to_utc_range(day, timezone_name)
    return f"[{start_utc:%Y%m%d%H%M} TO {end_utc:%Y%m%d%H%M}]"
