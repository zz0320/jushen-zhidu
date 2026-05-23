from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
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


def arxiv_date_ranges(day: date, timezone_name: str = "Asia/Shanghai") -> List[str]:
    start_utc, end_utc = local_day_to_utc_range(day, timezone_name)
    if start_utc.date() == end_utc.date():
        return [f"[{start_utc:%Y%m%d%H%M} TO {end_utc:%Y%m%d%H%M}]"]

    first_end = datetime.combine(start_utc.date(), time(23, 59), tzinfo=timezone.utc)
    second_start = datetime.combine(end_utc.date(), time.min, tzinfo=timezone.utc)
    return [
        f"[{start_utc:%Y%m%d%H%M} TO {first_end:%Y%m%d%H%M}]",
        f"[{second_start:%Y%m%d%H%M} TO {end_utc:%Y%m%d%H%M}]",
    ]


def arxiv_submitted_date_query(day: date, timezone_name: str = "Asia/Shanghai") -> str:
    terms = [f"submittedDate:{date_range}" for date_range in arxiv_date_ranges(day, timezone_name)]
    if len(terms) == 1:
        return terms[0]
    return "(" + " OR ".join(terms) + ")"
