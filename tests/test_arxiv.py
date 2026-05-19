from datetime import date

import httpx
from sqlmodel import Session, SQLModel, create_engine

from arxiv_daily.arxiv import build_search_query, fetch_papers_for_date, parse_atom_feed
from arxiv_daily.config import Settings
from arxiv_daily.defaults import init_default_config

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


def test_parse_atom_feed_extracts_entry():
    entries = parse_atom_feed(ATOM)

    assert len(entries) == 1
    assert entries[0].arxiv_id == "2605.00001v1"
    assert entries[0].title == "World Models for Vision-Language-Action Robot Manipulation"
    assert entries[0].authors == ["Alice Chen", "Bob Li"]
    assert entries[0].affiliations == ["Embodied AI Lab, Test University", "Robotics Institute"]
    assert entries[0].primary_category == "cs.RO"
    assert entries[0].pdf_url == "http://arxiv.org/pdf/2605.00001v1"


def test_build_search_query_uses_categories_and_submitted_date():
    query = build_search_query(["cs.RO", "cs.CV"], date(2026, 5, 15), "Asia/Shanghai")

    assert "(cat:cs.RO OR cat:cs.CV)" in query
    assert "submittedDate:[202605141600 TO 202605151559]" in query


def test_fetch_papers_scores_and_saves_relevant_paper():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        init_default_config(session)

        def fake_get(*args, **kwargs):
            return httpx.Response(200, text=ATOM, request=httpx.Request("GET", "https://example.test"))

        result = fetch_papers_for_date(session, date(2026, 5, 15), http_get=fake_get)
        assert result.fetched == 1
        assert result.saved == 1
        paper = session.get(__import__("arxiv_daily.models").models.Paper, "2605.00001v1")
        assert paper is not None
        assert paper.relevance_score > 0
        assert paper.affiliations == ["Embodied AI Lab, Test University", "Robotics Institute"]
        assert "world" in paper.matched_terms.lower()


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
            date(2026, 5, 15),
            http_get=fake_get,
            progress_callback=events.append,
        )

    assert result.saved == 1
    assert events[0]["stage"] == "preparing"
    assert events[-1]["stage"] == "complete"
    assert events[-1]["percent"] == 100
    assert any(event["stage"] == "processing" for event in events)


def test_fetch_papers_retries_429_with_wait(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(
        database_path=tmp_path / "test.sqlite3",
        report_dir=tmp_path,
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
            date(2026, 5, 15),
            settings=settings,
            http_get=fake_get,
            progress_callback=events.append,
            sleep_fn=waits.append,
        )

    assert result.saved == 1
    assert len(calls) == 2
    assert waits == [4.0]
    assert any(event["stage"] == "waiting" and event.get("retry") for event in events)
