from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from arxiv_daily.app import create_app
from arxiv_daily.config import Settings
from arxiv_daily.forest import build_forest_tile, classify_forest_kind, classify_growth, forest_scene_context
from arxiv_daily.models import Paper, PaperAbstractTranslation, PaperFullTextSummary, PaperSummary


def _paper(
    arxiv_id: str = "2605.00001v1",
    title: str = "Vision-Language-Action Robot Policy",
    score: float = 12.0,
    abstract: str = "A benchmark for embodied robot manipulation and navigation.",
    matched_keywords_json: str = '[{"keyword":"vision-language-action","group":"VLA","weight":3.5,"kind":"include"}]',
) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        abstract=abstract,
        authors_json='["Alice Chen", "Bob Li"]',
        primary_category="cs.RO",
        categories_json='["cs.RO", "cs.LG"]',
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
        fetched_for_date="2026-05-23",
        relevance_score=score,
        matched_keywords_json=matched_keywords_json,
    )


def test_forest_kind_classification_rules():
    assert classify_forest_kind(_paper(title="Open VLA for Dexterous Robots")).tree_label == "果树"
    assert classify_forest_kind(
        _paper(title="World Models for Robot Planning", matched_keywords_json='[{"keyword":"world model"}]')
    ).tree_label == "水晶树"
    assert classify_forest_kind(
        _paper(title="A Robotics Dataset Benchmark", matched_keywords_json='[{"keyword":"benchmark"}]')
    ).tree_label == "石碑树"
    assert classify_forest_kind(
        _paper(
            title="Robotics Control for Humanoids",
            abstract="A robot control method.",
            matched_keywords_json='[{"keyword":"robotics"}]',
        )
    ).tree_label == "机械松树"
    assert classify_forest_kind(
        _paper(
            title="Vision-Language Navigation with Self Awareness",
            abstract="An agent follows routes in indoor scenes.",
            matched_keywords_json='[{"keyword":"navigation"},{"keyword":"data engine","group":"World Models and Data Loop"}]',
        )
    ).tree_label == "路标树"
    assert classify_forest_kind(
        _paper(
            title="Unrelated Language Model",
            score=1.0,
            abstract="A carefully evaluated paper about tokenization.",
            matched_keywords_json="[]",
        )
    ).tree_label == "普通树"


def test_forest_growth_stage_uses_best_available_summary_state():
    paper = _paper()
    assert classify_growth(paper.arxiv_id, {}, {}, {}).label == "树苗"
    assert classify_growth(
        paper.arxiv_id,
        {paper.arxiv_id: PaperAbstractTranslation(arxiv_id=paper.arxiv_id, content="译文", model="fake")},
        {},
        {},
    ).label == "幼树"
    assert classify_growth(
        paper.arxiv_id,
        {},
        {paper.arxiv_id: PaperSummary(arxiv_id=paper.arxiv_id, content="摘要", model="fake")},
        {},
    ).label == "大树"
    assert classify_growth(
        paper.arxiv_id,
        {},
        {},
        {paper.arxiv_id: PaperFullTextSummary(arxiv_id=paper.arxiv_id, content="全文", model="fake")},
    ).label == "古树"


def test_forest_tile_visual_seed_is_stable_for_same_day_and_paper():
    paper = _paper(score=32.0)
    first = build_forest_tile(paper, date(2026, 5, 23), 1, {}, {}, {})
    second = build_forest_tile(paper, date(2026, 5, 23), 1, {}, {}, {})
    other_day = build_forest_tile(paper, date(2026, 5, 24), 1, {}, {}, {})

    assert first["seed"] == second["seed"]
    assert first["land"] == second["land"]
    assert first["rarity"] == "legendary"
    assert first["seed"] != other_day["seed"]


def test_forest_tile_only_grows_after_ai_summary():
    paper = _paper()
    translated = build_forest_tile(
        paper,
        date(2026, 5, 23),
        1,
        {paper.arxiv_id: PaperAbstractTranslation(arxiv_id=paper.arxiv_id, content="译文", model="fake")},
        {},
        {},
    )
    summarized = build_forest_tile(
        paper,
        date(2026, 5, 23),
        1,
        {},
        {paper.arxiv_id: PaperSummary(arxiv_id=paper.arxiv_id, content="摘要", model="fake")},
        {},
    )

    assert translated["growth"] == "translation"
    assert translated["summarized"] is False
    assert translated["plant_stage"] == "sapling"
    assert summarized["summarized"] is True
    assert summarized["plant_stage"] == "tree"


def test_forest_scene_context_is_stable_for_calendar_day():
    spring = forest_scene_context(date(2026, 5, 23))
    winter = forest_scene_context(date(2026, 12, 23))

    assert spring["season_key"] == "spring"
    assert spring["season_label"] == "春林"
    assert " · " in spring["badge"]
    assert winter["season_key"] == "winter"


def test_forest_api_returns_tiles_and_filtering(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(_paper(arxiv_id="2605.00001v1", title="Open VLA Robot Policy", score=20.0))
        session.add(
            _paper(
                arxiv_id="2605.00002v1",
                title="A Plain Optimization Paper",
                score=2.0,
                abstract="A paper about numerical optimization.",
                matched_keywords_json="[]",
            )
        )
        session.add(PaperSummary(arxiv_id="2605.00001v1", content="摘要", model="fake"))
        session.commit()

    client = TestClient(app)
    payload = client.get("/api/forest?date=2026-05-23").json()
    vla_payload = client.get("/api/forest?date=2026-05-23&filter=vla").json()
    summarized_payload = client.get("/api/forest?date=2026-05-23&filter=summarized").json()
    unsummarized_payload = client.get("/api/forest?date=2026-05-23&filter=unsummarized").json()

    assert payload["date"] == "2026-05-23"
    assert payload["scene"]["season_key"] == "spring"
    assert payload["counts"]["total"] == 2
    assert payload["tiles"][0]["tree_label"] == "果树"
    assert payload["tiles"][0]["growth_label"] == "大树"
    assert len(vla_payload["tiles"]) == 1
    assert len(summarized_payload["tiles"]) == 1
    assert summarized_payload["tiles"][0]["arxiv_id"] == "2605.00001v1"
    assert len(unsummarized_payload["tiles"]) == 1
    assert unsummarized_payload["tiles"][0]["arxiv_id"] == "2605.00002v1"


def test_forest_page_renders_tile_grid_and_details(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(_paper(arxiv_id="2605.00003v1", title="World Models for Robot Control", score=24.0))
        session.add(PaperFullTextSummary(arxiv_id="2605.00003v1", content="全文", model="fake"))
        session.commit()

    response = TestClient(app).get("/forest?date=2026-05-23")

    assert response.status_code == 200
    assert "论文森林" in response.text
    assert "data-forest-grove" in response.text
    assert "data-forest-tile" in response.text
    assert "forest-mote" in response.text
    assert "forest-inspector-plant" in response.text
    assert "data-forest-detail-sprite" in response.text
    assert "forest-status-pixels" in response.text
    assert "forest-growth-diary" in response.text
    assert "forest-season-badge" in response.text
    assert "forest-growth-status-badge" in response.text
    assert "data-forest-growth-fill" in response.text
    assert "data-forest-grown-visible" in response.text
    assert "分类树林" in response.text
    assert "--scatter-x" not in response.text
    assert "--scatter-y" not in response.text
    assert "水晶树" not in response.text
    assert "果树" not in response.text
    assert "机械松树" not in response.text
    assert "路标树" not in response.text
    assert "普通树" not in response.text
    assert "forest-focus-plot" not in response.text
    assert "data-forest-focus-start" not in response.text
    assert "forest-focus-harvest-badge" not in response.text
    assert "专注苗圃" not in response.text
    assert 'data-forest-season="spring"' in response.text
    assert "春林" in response.text
    assert 'data-growth-step="full_text"' in response.text
    assert "论文成长进度" in response.text
    assert "is-full-text-plant" in response.text
    assert "已成长" in response.text
    assert "树苗" in response.text
    assert "Embodied AI" in response.text
    assert "Manipulation" in response.text
    assert "Navigation" in response.text
    assert "Simulation" in response.text
    assert "Other" in response.text
    assert "未做 AI 总结" in response.text
    assert "已有单篇/全文总结" in response.text
    assert "古树" in response.text


def test_forest_page_marks_saplings_and_grown_trees(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        session.add(_paper(arxiv_id="2605.00004v1", title="Open VLA Robot Policy", score=20.0))
        session.add(
            _paper(
                arxiv_id="2605.00005v1",
                title="A Plain Optimization Paper",
                score=2.0,
                abstract="A paper about numerical optimization.",
                matched_keywords_json="[]",
            )
        )
        session.add(PaperSummary(arxiv_id="2605.00004v1", content="摘要", model="fake"))
        session.commit()

    response = TestClient(app).get("/forest?date=2026-05-23")

    assert response.status_code == 200
    assert 'data-plant-stage="tree"' in response.text
    assert 'data-plant-stage="sapling"' in response.text
    assert "/forest/generated/tree-vla-" in response.text
    assert "/forest/generated/sapling-other-" in response.text
    assert 'data-summarized="true"' in response.text
    assert 'data-summarized="false"' in response.text


def test_forest_page_handles_empty_and_invalid_dates(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    client = TestClient(app)

    empty_response = client.get("/forest?date=2026-05-24")
    invalid_response = client.get("/forest?date=not-a-date")

    assert empty_response.status_code == 200
    assert "这一天还没有森林" in empty_response.text
    assert invalid_response.status_code == 200
    assert "无法识别" in invalid_response.text
