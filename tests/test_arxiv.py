from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from sqlmodel import Session, SQLModel, create_engine, select

from arxiv_daily.arxiv import (
    FetchQuotaExceeded,
    build_search_query,
    fetch_papers_for_date,
    fetch_quota_status,
    parse_atom_feed,
    parse_atom_page,
)
from arxiv_daily.config import Settings
from arxiv_daily.defaults import init_default_config
from arxiv_daily.models import ArxivFetchRun, ArxivPageCache, Paper

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2605.00001v1</id>
    <updated>2026-05-15T12:00:00Z</updated>
    <published>2026-05-15T12:00:00Z</published>
    <title>World Models for Vision-Language-Action Robot Manipulation</title>
    <summary>We introduce a robot dataset and benchmark for embodied intelligence.</summary>
    <author>
      <name>Alice Chen</name>
      <arxiv:affiliation>Embodied AI Lab, Test University</arxiv:affiliation>
    </author>
    <author>
      <name>Bob Li</name>
      <arxiv:affiliation>Robotics Institute</arxiv:affiliation>
    </author>
    <category term="cs.RO" />
    <category term="cs.LG" />
    <arxiv:primary_category term="cs.RO" />
    <link href="http://arxiv.org/abs/2605.00001v1" rel="alternate" type="text/html" />
    <link title="pdf" href="http://arxiv.org/pdf/2605.00001v1" rel="related" type="application/pdf" />
  </entry>
</feed>
"""

ATOM_WITH_OPENSEARCH = ATOM.replace(
    'xmlns:arxiv="http://arxiv.org/schemas/atom">',
    'xmlns:arxiv="http://arxiv.org/schemas/atom"\n      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
    "\n  <opensearch:totalResults>1</opensearch:totalResults>"
    "\n  <opensearch:startIndex>0</opensearch:startIndex>"
    "\n  <opensearch:itemsPerPage>1</opensearch:itemsPerPage>",
)

EMPTY_ATOM_WITH_OPENSEARCH = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>0</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
</feed>
"""


def test_parse_atom_feed_extracts_entry():
    entries = parse_atom_feed(ATOM)

    assert len(entries) == 1
    assert entries[0].arxiv_id == "2605.00001v1"
    assert entries[0].title == "World Models for Vision-Language-Action Robot Manipulation"
    assert entries[0].authors == ["Alice Chen", "Bob Li"]
    assert entries[0].affiliations == ["Embodied AI Lab, Test University", "Robotics Institute"]
    assert entries[0].primary_category == "cs.RO"
    assert entries[0].pdf_url == "http://arxiv.org/pdf/2605.00001v1"


def test_parse_atom_page_extracts_opensearch_metadata():
    page = parse_atom_page(ATOM_WITH_OPENSEARCH)

    assert page.total_results == 1
    assert page.start_index == 0
    assert page.items_per_page == 1
    assert page.entries[0].arxiv_id == "2605.00001v1"


def test_build_search_query_uses_categories_and_submitted_date():
    query = build_search_query(["cs.RO", "cs.CV"], date(2026, 5, 14), "Asia/Shanghai")

    assert "(cat:cs.RO OR cat:cs.CV)" in query
    assert "submittedDate:[202605131800 TO 202605132359]" in query
    assert "submittedDate:[202605140000 TO 202605141759]" in query
    assert " OR " in query


def test_build_search_query_returns_empty_for_days_without_regular_batch():
    query = build_search_query(["cs.RO", "cs.CV"], date(2026, 5, 30), "Asia/Shanghai")

    assert query == ""


def test_build_search_query_uses_sunday_announcement_batch():
    query = build_search_query(["cs.RO", "cs.CV"], date(2026, 5, 31), "Asia/Shanghai")

    assert "submittedDate:[202605281800 TO 202605282359]" in query
    assert "submittedDate:[202605290000 TO 202605291759]" in query


def test_fetch_papers_scores_and_saves_relevant_paper():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        init_default_config(session)

        def fake_get(*args, **kwargs):
            return httpx.Response(200, text=ATOM, request=httpx.Request("GET", "https://example.test"))

        result = fetch_papers_for_date(session, date(2026, 5, 14), http_get=fake_get)
        assert result.fetched == 1
        assert result.saved == 1
        paper = session.get(__import__("arxiv_daily.models").models.Paper, "2605.00001v1")
        assert paper is not None
        assert paper.relevance_score > 0
        assert paper.affiliations == ["Embodied AI Lab, Test University", "Robotics Institute"]
        assert "world" in paper.matched_terms.lower()


def test_fetch_papers_skips_network_for_day_without_regular_batch():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        init_default_config(session)

        def fake_get(*args, **kwargs):
            raise AssertionError("weekend batch should not call arXiv")

        result = fetch_papers_for_date(session, date(2026, 5, 30), http_get=fake_get)

    assert result.fetched == 0
    assert result.network_requests == 0
    assert result.query == ""


def test_fetch_papers_refreshes_existing_paper_timestamp(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", arxiv_cache_enabled=False)
    with Session(engine) as session:
        init_default_config(session)

        def fake_get(*args, **kwargs):
            return httpx.Response(200, text=ATOM, request=httpx.Request("GET", "https://example.test"))

        fetch_papers_for_date(session, date(2026, 5, 14), settings=settings, http_get=fake_get)
        paper = session.get(Paper, "2605.00001v1")
        assert paper is not None
        old_refreshed_at = datetime(2026, 1, 1)
        paper.refreshed_at = old_refreshed_at
        session.add(paper)
        session.commit()

        result = fetch_papers_for_date(session, date(2026, 5, 14), settings=settings, http_get=fake_get)
        paper = session.get(Paper, "2605.00001v1")

    assert result.saved == 0
    assert result.matched == 1
    assert result.updated == 1
    assert paper is not None
    assert paper.refreshed_at > old_refreshed_at


def test_fetch_papers_reports_progress():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        init_default_config(session)
        events = []

        def fake_get(*args, **kwargs):
            return httpx.Response(200, text=ATOM, request=httpx.Request("GET", "https://example.test"))

        result = fetch_papers_for_date(
            session,
            date(2026, 5, 14),
            http_get=fake_get,
            progress_callback=events.append,
        )

    assert result.saved == 1
    assert events[0]["stage"] == "preparing"
    assert events[-1]["stage"] == "complete"
    assert events[-1]["percent"] == 100
    assert any(event["stage"] == "processing" for event in events)


def test_fetch_papers_uses_cached_page_on_repeated_query(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    with Session(engine) as session:
        init_default_config(session)
        calls = []
        events = []

        def fake_get(*args, **kwargs):
            calls.append(kwargs)
            return httpx.Response(200, text=ATOM, request=httpx.Request("GET", "https://example.test"))

        first = fetch_papers_for_date(session, date(2026, 5, 14), settings=settings, http_get=fake_get)
        second = fetch_papers_for_date(
            session,
            date(2026, 5, 14),
            settings=settings,
            http_get=fake_get,
            progress_callback=events.append,
        )

    assert first.network_requests == 1
    assert second.network_requests == 0
    assert second.cached_pages == 1
    assert len(calls) == 1
    assert any(event["stage"] == "cached" for event in events)


def test_fetch_papers_bypasses_stale_empty_cache_for_recent_day(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(
        database_path=tmp_path / "test.sqlite3",
        arxiv_page_size=1,
        arxiv_max_results=1,
        arxiv_empty_cache_ttl_seconds=1,
    )
    target_day = datetime.now(ZoneInfo(settings.timezone)).date()
    with Session(engine) as session:
        init_default_config(session)
        calls = []

        def fake_get(*args, **kwargs):
            calls.append(kwargs)
            response_text = EMPTY_ATOM_WITH_OPENSEARCH if len(calls) == 1 else ATOM_WITH_OPENSEARCH
            return httpx.Response(200, text=response_text, request=httpx.Request("GET", "https://example.test"))

        empty = fetch_papers_for_date(session, target_day, settings=settings, http_get=fake_get)
        cached_page = session.exec(select(ArxivPageCache)).first()
        assert cached_page is not None
        cached_page.fetched_at = datetime(2026, 1, 1)
        session.add(cached_page)
        session.commit()

        refreshed = fetch_papers_for_date(session, target_day, settings=settings, http_get=fake_get)

    assert empty.fetched == 0
    assert refreshed.saved == 1
    assert refreshed.network_requests == 1
    assert refreshed.cached_pages == 0
    assert len(calls) == 2


def test_fetch_papers_uses_total_results_to_avoid_empty_extra_page(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(
        database_path=tmp_path / "test.sqlite3",
        arxiv_page_size=1,
        arxiv_max_results=3,
    )
    with Session(engine) as session:
        init_default_config(session)
        calls = []

        def fake_get(*args, **kwargs):
            calls.append(kwargs)
            return httpx.Response(
                200,
                text=ATOM_WITH_OPENSEARCH,
                request=httpx.Request("GET", "https://example.test"),
            )

        result = fetch_papers_for_date(session, date(2026, 5, 14), settings=settings, http_get=fake_get)

    assert result.network_requests == 1
    assert result.fetched == 1
    assert len(calls) == 1


def test_fetch_papers_force_refresh_ignores_cached_page(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", arxiv_daily_network_fetch_limit=2)
    with Session(engine) as session:
        init_default_config(session)
        calls = []

        def fake_get(*args, **kwargs):
            calls.append(kwargs)
            return httpx.Response(200, text=ATOM, request=httpx.Request("GET", "https://example.test"))

        fetch_papers_for_date(session, date(2026, 5, 14), settings=settings, http_get=fake_get)
        result = fetch_papers_for_date(
            session,
            date(2026, 5, 14),
            settings=settings,
            http_get=fake_get,
            force_refresh=True,
        )

    assert result.network_requests == 1
    assert result.cached_pages == 0
    assert result.saved == 0
    assert result.updated == 1
    assert result.daily_network_fetch_used == 1
    assert len(calls) == 2


def test_fetch_papers_blocks_realtime_refresh_after_daily_limit(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", arxiv_daily_network_fetch_limit=1)
    with Session(engine) as session:
        init_default_config(session)
        calls = []

        def fake_get(*args, **kwargs):
            calls.append(kwargs)
            return httpx.Response(200, text=ATOM, request=httpx.Request("GET", "https://example.test"))

        first = fetch_papers_for_date(session, date(2026, 5, 14), settings=settings, http_get=fake_get)
        cached = fetch_papers_for_date(session, date(2026, 5, 14), settings=settings, http_get=fake_get)
        try:
            fetch_papers_for_date(
                session,
                date(2026, 5, 14),
                settings=settings,
                http_get=fake_get,
                force_refresh=True,
            )
        except FetchQuotaExceeded as exc:
            error = str(exc)
        else:  # pragma: no cover - assertion guard
            error = ""

    assert first.daily_network_fetch_used == 1
    assert cached.network_requests == 0
    assert cached.daily_network_fetch_used == 1
    assert len(calls) == 1
    assert "今日实时抓取次数已用完" in error


def test_fetch_quota_counts_only_running_or_completed_runs_with_new_papers(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", arxiv_daily_network_fetch_limit=5)
    run_date = datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
    with Session(engine) as session:
        session.add(
            ArxivFetchRun(
                target_date="2026-05-14",
                run_date=run_date,
                status="failed",
                network_requests=0,
                message="服务重启后任务已中止。",
            )
        )
        session.add(
            ArxivFetchRun(
                target_date="2026-05-14",
                run_date=run_date,
                status="failed",
                network_requests=1,
                message="arXiv request failed.",
            )
        )
        session.add(
            ArxivFetchRun(
                target_date="2026-05-14",
                run_date=run_date,
                status="completed",
                network_requests=1,
                saved_papers=0,
                message="No matching new papers.",
            )
        )
        session.add(
            ArxivFetchRun(
                target_date="2026-05-14",
                run_date=run_date,
                status="completed",
                network_requests=1,
                saved_papers=2,
            )
        )
        session.add(
            ArxivFetchRun(
                target_date="2026-05-14",
                run_date=run_date,
                status="running",
            )
        )
        session.commit()

        status = fetch_quota_status(session, date(2026, 5, 14), settings)

    assert status.used == 1
    assert status.remaining == 4


def test_fetch_papers_retries_429_with_wait(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(
        database_path=tmp_path / "test.sqlite3",
        arxiv_retry_count=2,
        arxiv_request_delay_seconds=3.2,
    )
    with Session(engine) as session:
        init_default_config(session)
        calls = []
        waits = []
        events = []

        def fake_get(*args, **kwargs):
            calls.append(kwargs)
            request = httpx.Request("GET", "https://example.test")
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "4"}, request=request)
            return httpx.Response(200, text=ATOM, request=request)

        result = fetch_papers_for_date(
            session,
            date(2026, 5, 14),
            settings=settings,
            http_get=fake_get,
            progress_callback=events.append,
            sleep_fn=waits.append,
        )

    assert result.saved == 1
    assert len(calls) == 2
    assert waits == [4.0]
    assert any(event["stage"] == "waiting" and event.get("retry") for event in events)
