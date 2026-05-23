from datetime import date

from arxiv_daily.dates import arxiv_date_range, arxiv_date_ranges, arxiv_submitted_date_query, local_day_to_utc_range


def test_beijing_day_converts_to_utc_range():
    start, end = local_day_to_utc_range(date(2026, 5, 15), "Asia/Shanghai")

    assert start.strftime("%Y%m%d%H%M") == "202605141600"
    assert end.strftime("%Y%m%d%H%M") == "202605151559"


def test_arxiv_date_range_format():
    assert arxiv_date_range(date(2026, 5, 15), "Asia/Shanghai") == "[202605141600 TO 202605151559]"


def test_arxiv_date_ranges_split_utc_midnight():
    assert arxiv_date_ranges(date(2026, 5, 15), "Asia/Shanghai") == [
        "[202605141600 TO 202605142359]",
        "[202605150000 TO 202605151559]",
    ]


def test_arxiv_submitted_date_query_combines_split_ranges():
    assert arxiv_submitted_date_query(date(2026, 5, 15), "Asia/Shanghai") == (
        "(submittedDate:[202605141600 TO 202605142359] "
        "OR submittedDate:[202605150000 TO 202605151559])"
    )
