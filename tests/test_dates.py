from datetime import date

from arxiv_daily.dates import (
    arxiv_batch_date_ranges,
    arxiv_batch_utc_range,
    arxiv_date_range,
    arxiv_date_ranges,
    arxiv_submitted_date_query,
    local_day_to_utc_range,
)


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


def test_arxiv_submitted_date_query_uses_arxiv_cutoff_batch():
    assert arxiv_submitted_date_query(date(2026, 5, 14), "Asia/Shanghai") == (
        "(submittedDate:[202605131800 TO 202605132359] "
        "OR submittedDate:[202605140000 TO 202605141759])"
    )


def test_monday_arxiv_batch_covers_weekend_submission_window():
    assert arxiv_batch_date_ranges(date(2026, 6, 1)) == [
        "[202605291800 TO 202605292359]",
        "[202605300000 TO 202605302359]",
        "[202605310000 TO 202605312359]",
        "[202606010000 TO 202606011759]",
    ]


def test_sunday_arxiv_batch_covers_thursday_to_friday_cutoff():
    assert arxiv_batch_date_ranges(date(2026, 5, 31)) == [
        "[202605281800 TO 202605282359]",
        "[202605290000 TO 202605291759]",
    ]


def test_friday_and_saturday_have_no_regular_arxiv_batch():
    assert arxiv_batch_utc_range(date(2026, 5, 29)) is None
    assert arxiv_batch_date_ranges(date(2026, 5, 30)) == []
