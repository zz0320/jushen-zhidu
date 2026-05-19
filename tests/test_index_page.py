from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from arxiv_daily.app import create_app
from arxiv_daily.config import Settings
from arxiv_daily.models import Paper


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
