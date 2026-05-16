from datetime import date

from arxiv_daily.dates import arxiv_date_range, local_day_to_utc_range


def test_beijing_day_converts_to_utc_range():
    start, end = local_day_to_utc_range(date(2026, 5, 15), "Asia/Shanghai")

    assert start.strftime("%Y%m%d%H%M") == "202605141600"
    assert end.strftime("%Y%m%d%H%M") == "202605151559"


def test_arxiv_date_range_format():
    assert arxiv_date_range(date(2026, 5, 15), "Asia/Shanghai") == "[202605141600 TO 202605151559]"

