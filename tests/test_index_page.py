import threading
import time
from datetime import date, datetime, timezone

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import arxiv_daily.app as app_module
from arxiv_daily.app import create_app
from arxiv_daily.arxiv import FetchResult
from arxiv_daily.config import Settings
from arxiv_daily.dates import arxiv_date_range, arxiv_submitted_date_query
from arxiv_daily.models import (
    ArxivFetchRun,
    ArxivPageCache,
    Paper,
    PaperAbstractTranslation,
    PaperFullTextSummary,
    PaperSummary,
    UserPaperFavorite,
)
from auth_helpers import authenticated_client


def test_index_paper_card_exposes_ai_actions(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.18722v1",
                title="Open VLA for Bimanual Dexterity",
                abstract="A long abstract about embodied AI and robot manipulation.",
                authors_json='["Alice Chen"]',
                affiliations_json='["Robotics Institute"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                published_at=datetime(2026, 5, 18, 17, 50, tzinfo=timezone.utc),
                abs_url="https://arxiv.org/abs/2605.18722v1",
                pdf_url="https://arxiv.org/pdf/2605.18722v1",
                fetched_for_date="2026-05-19",
                relevance_score=35.4,
                matched_keywords_json='[{"keyword":"robot","group":"Robotics","weight":2.5,"kind":"include"}]',
            )
        )
        session.commit()

    html = authenticated_client(app, engine).get("/?day=2026-05-19").text

    assert "Robotics Institute" in html
    assert "data-summary-job-url=\"/summary-jobs/papers/2605.18722v1/all\"" in html
    assert "生成三项" in html
    assert "data-summary-job-url=\"/summary-jobs/paper-abstract-translation\"" not in html
    assert "data-summary-job-url=\"/summary-jobs/paper-full-text\"" not in html
    assert "data-progress-summary=\"true\"" in html


def test_index_paper_card_shows_summary_previews(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.18723v1",
                title="Robot Policy Preview",
                abstract="A robot policy abstract.",
                authors_json='["Alice Chen"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-19",
                relevance_score=12.0,
                matched_keywords_json='[{"keyword":"robot","group":"Robotics","weight":2.5,"kind":"include"}]',
            )
        )
        session.add(
            PaperSummary(
                arxiv_id="2605.18723v1",
                content="1. 研究问题\n机器人需要在复杂环境中完成稳健操作。\n2. 方法概述\n提出一个多模态策略。",
                model="fake-qwen",
            )
        )
        session.add(
            PaperFullTextSummary(
                arxiv_id="2605.18723v1",
                content="基于 arXiv PDF 全文文本提取。\n\n1. 实验设置与主要结果\n全文显示了更完整的实验细节。",
                model="fake-qwen",
            )
        )
        session.commit()

    html = authenticated_client(app, engine).get("/?day=2026-05-19").text

    assert "摘要总结" in html
    assert "全文总结" in html
    assert "机器人需要在复杂环境中完成稳健操作" in html
    assert "全文显示了更完整的实验细节" in html


def test_index_paper_card_renders_full_insight_blocks(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    long_body = "\n".join(
        [
            "1. 研究问题",
            "这是一段用于拉长总览内容的说明。" * 18,
            "2. 方法概述",
            "模型通过视觉提示和语言条件共同完成预测。" * 18,
            "最终完整展示标记",
        ]
    )
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.18728v1",
                title="Long Insight Preview",
                abstract="A robot paper abstract.",
                authors_json='["Alice Chen"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-19",
                relevance_score=18.0,
            )
        )
        session.add(PaperSummary(arxiv_id="2605.18728v1", content=long_body, model="fake-qwen"))
        session.add(PaperFullTextSummary(arxiv_id="2605.18728v1", content=long_body, model="fake-qwen"))
        session.commit()

    html = authenticated_client(app, engine).get("/?day=2026-05-19").text

    assert "paper-card-insights-expanded" in html
    assert "paper-insight-disclosure" in html
    assert "<summary class=\"paper-insight-row-head\">" in html
    assert "展开查看更多" in html
    assert "这是一段用于拉长总览内容的说明" in html
    assert "paper-insight-content" in html
    assert "最终完整展示标记" in html


def test_paper_detail_uses_combined_insight_action(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.18725v1",
                title="Paper Detail Action",
                abstract="A robot paper abstract.",
                authors_json='["Alice Chen"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-19",
                relevance_score=18.0,
            )
        )
        session.add(
            PaperAbstractTranslation(
                arxiv_id="2605.18725v1",
                title_content="论文详情动作",
                content="一段中文摘要。",
                model="fake-qwen",
            )
        )
        session.add(
            PaperSummary(
                arxiv_id="2605.18725v1",
                content="摘要总结内容。",
                model="fake-qwen",
            )
        )
        session.add(
            PaperFullTextSummary(
                arxiv_id="2605.18725v1",
                content="全文总结内容。",
                model="fake-qwen",
                figures_json='[{"url":"/static/generated/figures/2605.18725v1-figure-1-p2.png","page":2,"index":1,"caption":"PDF 第 2 页图片摘选"}]',
            )
        )
        session.commit()

    html = authenticated_client(app, engine).get("/papers/2605.18725v1").text

    assert "当日总览" in html
    assert "action=\"/papers/2605.18725v1/summarize-all\"" in html
    assert "data-summary-job-url=\"/summary-jobs/papers/2605.18725v1/all\"" in html
    assert "刷新三项" in html
    assert "文字总结" in html
    assert "关键图片总结" in html
    assert "paper-figure-album" in html
    assert "data-gallery-image" in html
    assert "paper-figure-strip" not in html
    assert "/static/generated/figures/2605.18725v1-figure-1-p2.png" in html
    assert "data-summary-job-url=\"/summary-jobs/paper-abstract-translation\"" not in html
    assert "data-summary-job-url=\"/summary-jobs/paper-full-text\"" not in html


def test_papers_workspace_lists_day_papers(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.18724v1",
                title="Paper Workspace Entry",
                abstract="A robot paper abstract.",
                authors_json='["Alice Chen"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-19",
                relevance_score=18.0,
                matched_keywords_json='[{"keyword":"robot","group":"Robotics","weight":2.5,"kind":"include"}]',
            )
        )
        session.commit()

    html = authenticated_client(app, engine).get("/papers?day=2026-05-19").text

    assert "单篇论文" in html
    assert "Paper Workspace Entry" in html
    assert "Paper not found" not in html


def test_paper_favorites_are_user_scoped_and_filterable(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.18730v1",
                title="Favorite Robot Paper",
                abstract="A favorite robot paper abstract.",
                authors_json='["Alice Chen"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-19",
                relevance_score=18.0,
            )
        )
        session.add(
            Paper(
                arxiv_id="2605.18731v1",
                title="Unmarked Robot Paper",
                abstract="An unmarked robot paper abstract.",
                authors_json='["Bob Lee"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-19",
                relevance_score=8.0,
            )
        )
        session.commit()

    admin = authenticated_client(app, engine)
    response = admin.post(
        "/papers/2605.18730v1/favorite",
        data={"next": "/papers?day=2026-05-19"},
        headers={"accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["favorite"] is True
    with Session(engine) as session:
        favorite = session.exec(
            select(UserPaperFavorite).where(UserPaperFavorite.arxiv_id == "2605.18730v1")
        ).first()
        assert favorite is not None

    day_html = admin.get("/papers?day=2026-05-19").text
    assert "Favorite Robot Paper" in day_html
    assert "已收藏" in day_html
    assert 'href="/papers?day=2026-05-19&favorites=true"' in day_html

    filtered_html = admin.get("/papers?day=2026-05-19&favorites=true").text
    assert "Favorite Robot Paper" in filtered_html
    assert "Unmarked Robot Paper" not in filtered_html

    favorites_html = admin.get("/favorites").text
    assert "我的收藏" in favorites_html
    assert "Favorite Robot Paper" in favorites_html
    assert "Unmarked Robot Paper" not in favorites_html

    viewer = authenticated_client(app, engine, role="viewer")
    viewer_favorites = viewer.get("/favorites").text
    assert "Favorite Robot Paper" not in viewer_favorites
    assert "还没有收藏论文" in viewer_favorites


def test_forest_marks_favorite_tiles_for_current_user(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.18732v1",
                title="Favorite Forest Paper",
                abstract="A favorite forest paper abstract.",
                authors_json='["Alice Chen"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-19",
                relevance_score=18.0,
                matched_keywords_json='[{"keyword":"robot","group":"Robotics","weight":2.5,"kind":"include"}]',
            )
        )
        session.commit()

    client = authenticated_client(app, engine)
    client.post(
        "/papers/2605.18732v1/favorite",
        data={"next": "/forest?date=2026-05-19"},
        headers={"accept": "application/json"},
    )

    html = client.get("/forest?date=2026-05-19").text
    assert "Favorite Forest Paper" in html
    assert 'data-forest-detail-favorite-form' in html
    assert 'data-favorite="true"' in html

    payload = client.get("/api/forest?date=2026-05-19").json()
    assert payload["tiles"][0]["favorite"] is True


def test_clear_day_cache_removes_day_data_but_preserves_limit_runs(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    day = "2026-05-19"
    other_day = "2026-05-20"
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.18726v1",
                title="Daily cache target",
                abstract="A target day paper.",
                authors_json='["Alice Chen"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date=day,
                relevance_score=18.0,
            )
        )
        session.add(
            Paper(
                arxiv_id="2605.18727v1",
                title="Other day paper",
                abstract="An other day paper.",
                authors_json='["Bob Lee"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date=other_day,
                relevance_score=10.0,
            )
        )
        session.add(PaperAbstractTranslation(arxiv_id="2605.18726v1", title_content="目标", content="译文", model="fake"))
        session.add(PaperSummary(arxiv_id="2605.18726v1", content="摘要", model="fake"))
        session.add(PaperFullTextSummary(arxiv_id="2605.18726v1", content="全文", model="fake"))
        session.add(PaperSummary(arxiv_id="2605.18727v1", content="其他日摘要", model="fake"))
        session.add(
            ArxivPageCache(
                cache_key="target-cache",
                query=f"(cat:cs.RO) AND submittedDate:{arxiv_date_range(date(2026, 5, 19), settings.timezone)}",
                start=0,
                page_size=100,
                response_text="<feed />",
            )
        )
        session.add(
            ArxivPageCache(
                cache_key="target-cache-split",
                query=f"(cat:cs.RO) AND {arxiv_submitted_date_query(date(2026, 5, 19), settings.timezone)}",
                start=0,
                page_size=100,
                response_text="<feed />",
            )
        )
        session.add(
            ArxivPageCache(
                cache_key="other-cache",
                query=f"(cat:cs.RO) AND submittedDate:{arxiv_date_range(date(2026, 5, 20), settings.timezone)}",
                start=0,
                page_size=100,
                response_text="<feed />",
            )
        )
        session.add(ArxivFetchRun(target_date=day, run_date=day, status="completed", network_requests=1))
        session.commit()

    response = authenticated_client(app, engine).post(f"/day-cache/{day}/clear", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/?day={day}&message=")
    with Session(engine) as session:
        assert session.get(Paper, "2605.18726v1") is None
        assert session.get(Paper, "2605.18727v1") is not None
        assert session.exec(select(PaperSummary).where(PaperSummary.arxiv_id == "2605.18726v1")).first() is None
        assert session.exec(select(PaperFullTextSummary).where(PaperFullTextSummary.arxiv_id == "2605.18726v1")).first() is None
        assert session.exec(select(PaperAbstractTranslation).where(PaperAbstractTranslation.arxiv_id == "2605.18726v1")).first() is None
        assert session.get(ArxivPageCache, "target-cache") is None
        assert session.get(ArxivPageCache, "target-cache-split") is None
        assert session.get(ArxivPageCache, "other-cache") is not None
        assert session.exec(select(ArxivFetchRun).where(ArxivFetchRun.target_date == day)).first() is not None


def test_clear_all_cache_removes_all_content_data_but_preserves_limit_runs(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    figure_dir = tmp_path / "figures"
    figure_dir.mkdir()
    figure_path = figure_dir / "2605.18726v1-figure-1-p1.png"
    figure_path.write_bytes(b"fake image")
    monkeypatch.setattr(app_module, "DEFAULT_FIGURE_OUTPUT_DIR", figure_dir)

    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.18726v1",
                title="Daily cache target",
                abstract="A target day paper.",
                authors_json='["Alice Chen"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-19",
                relevance_score=18.0,
            )
        )
        session.add(
            Paper(
                arxiv_id="2605.18727v1",
                title="Other day paper",
                abstract="An other day paper.",
                authors_json='["Bob Lee"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-20",
                relevance_score=10.0,
            )
        )
        session.add(PaperAbstractTranslation(arxiv_id="2605.18726v1", title_content="目标", content="译文", model="fake"))
        session.add(PaperSummary(arxiv_id="2605.18726v1", content="摘要", model="fake"))
        session.add(PaperFullTextSummary(arxiv_id="2605.18726v1", content="全文", model="fake"))
        session.add(
            ArxivPageCache(
                cache_key="target-cache",
                query="cat:cs.RO",
                start=0,
                page_size=100,
                response_text="<feed />",
            )
        )
        session.add(ArxivFetchRun(target_date="2026-05-19", run_date="2026-05-19", status="completed"))
        session.commit()

    client = authenticated_client(app, engine)
    html = client.get("/?day=2026-05-19").text
    assert "清理全部" in html

    response = client.post("/cache/clear", data={"day": "2026-05-19"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/?day=2026-05-19&message=")
    assert not figure_path.exists()
    with Session(engine) as session:
        assert session.exec(select(Paper)).all() == []
        assert session.exec(select(PaperSummary)).all() == []
        assert session.exec(select(PaperFullTextSummary)).all() == []
        assert session.exec(select(PaperAbstractTranslation)).all() == []
        assert session.exec(select(ArxivPageCache)).all() == []
        assert session.exec(select(ArxivFetchRun)).first() is not None


def test_app_startup_marks_stale_fetch_runs_failed(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    with Session(engine) as session:
        SQLModel.metadata.create_all(engine)
        session.add(ArxivFetchRun(target_date="2026-05-19", run_date="2026-05-19", status="running"))
        session.commit()

    create_app(settings=settings, engine=engine)

    with Session(engine) as session:
        run = session.exec(select(ArxivFetchRun).where(ArxivFetchRun.target_date == "2026-05-19")).first()
        assert run is not None
        assert run.status == "failed"
        assert "服务重启" in run.message


def test_fetch_job_reuses_active_job_for_same_day(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    started = threading.Event()
    release = threading.Event()

    def fake_fetch(*args, **kwargs):
        started.set()
        release.wait(timeout=2)
        return FetchResult(
            fetched=0,
            saved=0,
            skipped_no_keyword=0,
            skipped_excluded=0,
            query="fake",
        )

    monkeypatch.setattr(app_module, "fetch_papers_for_date", fake_fetch)
    client = authenticated_client(app, engine, role="editor")

    first = client.post("/fetch-jobs", data={"day": "2026-05-25"})
    try:
        assert first.status_code == 200
        first_job_id = first.json()["job_id"]
        assert started.wait(timeout=1)

        second = client.post("/fetch-jobs", data={"day": "2026-05-25"})

        assert second.status_code == 200
        assert second.json()["job_id"] == first_job_id
        assert second.json()["reused"] is True
    finally:
        release.set()


def test_fetch_job_stale_threshold_respects_long_arxiv_wait(tmp_path):
    settings = Settings(database_path=tmp_path / "test.sqlite3", request_timeout_seconds=30)

    stale_after = app_module._fetch_job_stale_after({"stage": "waiting", "wait_seconds": 240}, settings)

    assert stale_after >= 300


def test_empty_fetch_result_explains_no_arxiv_batch():
    message = app_module._message_from_fetch(
        FetchResult(
            fetched=0,
            saved=0,
            skipped_no_keyword=0,
            skipped_excluded=0,
            query="fake",
            network_requests=1,
        )
    )

    assert "没有返回这一天的论文" in message
    assert "联网请求 1 次" in message


def test_empty_fetch_result_explains_no_friday_saturday_batch():
    message = app_module._message_from_fetch(
        FetchResult(
            fetched=0,
            saved=0,
            skipped_no_keyword=0,
            skipped_excluded=0,
            query="fake",
            network_requests=1,
        ),
        date(2026, 5, 30),
    )

    assert "2026-05-30" in message
    assert "周五和周六没有常规公告" in message
    assert "周一公告批次" in message


def test_empty_fetch_job_stays_on_requested_day_and_reports_latest_available(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.29000v1",
                title="Latest Available Paper",
                abstract="A paper from the latest available arXiv batch.",
                authors_json='["Alice Chen"]',
                primary_category="cs.RO",
                categories_json='["cs.RO"]',
                fetched_for_date="2026-05-29",
                relevance_score=10.0,
            )
        )
        session.commit()

    def fake_fetch(*args, **kwargs):
        return FetchResult(
            fetched=0,
            saved=0,
            skipped_no_keyword=0,
            skipped_excluded=0,
            query="fake",
            network_requests=1,
        )

    monkeypatch.setattr(app_module, "fetch_papers_for_date", fake_fetch)
    client = authenticated_client(app, engine, role="editor")

    started = client.post("/fetch-jobs", data={"day": "2026-05-30"})
    assert started.status_code == 200
    job_id = started.json()["job_id"]
    payload = {}
    for _ in range(50):
        payload = client.get(f"/fetch-jobs/{job_id}").json()
        if payload.get("status") == "completed":
            break
        time.sleep(0.02)

    assert payload["status"] == "completed"
    assert payload["current_count"] == 0
    assert payload["latest_day"] == "2026-05-29"
    assert payload["redirect_url"] == "/?day=2026-05-30"
    assert "没有返回 2026-05-30 的论文" in payload["message"]
    assert "周五和周六没有常规公告" in payload["message"]
    assert "最近有论文的日期是 2026-05-29" in payload["message"]
