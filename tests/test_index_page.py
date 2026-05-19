from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from arxiv_daily.app import create_app
from arxiv_daily.config import Settings
from arxiv_daily.models import Paper, PaperFullTextSummary, PaperSummary


def test_index_paper_card_exposes_ai_actions(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3", report_dir=tmp_path)
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

    html = TestClient(app).get("/?day=2026-05-19").text

    assert "Robotics Institute" in html
    assert "data-summary-job-url=\"/summary-jobs/paper-abstract-translation\"" in html
    assert "data-summary-job-url=\"/summary-jobs/papers/2605.18722v1\"" in html
    assert "data-summary-job-url=\"/summary-jobs/paper-full-text\"" in html
    assert "正在执行智能任务" in html


def test_index_paper_card_shows_summary_previews(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "test.sqlite3", report_dir=tmp_path)
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

    html = TestClient(app).get("/?day=2026-05-19").text

    assert "摘要总结" in html
    assert "全文总结" in html
    assert "机器人需要在复杂环境中完成稳健操作" in html
    assert "全文显示了更完整的实验细节" in html
