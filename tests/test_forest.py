from datetime import date

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from arxiv_daily.app import create_app
from arxiv_daily.config import Settings
from arxiv_daily.forest import build_forest_tile, classify_forest_kind, classify_growth, forest_groves, forest_scene_context
from arxiv_daily.models import Paper, PaperAbstractTranslation, PaperFullTextSummary, PaperSummary
from auth_helpers import authenticated_client


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
    assert classify_forest_kind(_paper(title="Open VLA for Dexterous Robots")).tree_label == "基座树"
    assert classify_forest_kind(
        _paper(title="Embodied VLM for Robot Policies", matched_keywords_json='[{"keyword":"vlm"}]')
    ).label == "Foundation Model"
    assert classify_forest_kind(
        _paper(title="World Models for Robot Planning", matched_keywords_json='[{"keyword":"world model"}]')
    ).label == "Foundation Model"
    assert classify_forest_kind(
        _paper(title="World Action Models for Vision-Language-Action Control", matched_keywords_json='[{"keyword":"world action model"},{"keyword":"vla"}]')
    ).label == "Foundation Model"
    assert classify_forest_kind(
        _paper(title="VLA Reinforcement Learning for Robot Control", matched_keywords_json='[{"keyword":"vla reinforcement learning"}]')
    ).label == "Foundation Model"
    assert classify_forest_kind(
        _paper(
            title="EgoMimic: Learning Robot Policies from Egocentric Human Videos",
            abstract="A universal manipulation interface collects first-person human demonstrations.",
            matched_keywords_json='[{"keyword":"egocentric"},{"keyword":"umi"}]',
        )
    ).label == "Ego / UMI"
    assert classify_forest_kind(
        _paper(
            title="A Robotics Dataset Benchmark",
            abstract="A diagnostic benchmark and dataset for embodied agents.",
            matched_keywords_json='[{"keyword":"benchmark"}]',
        )
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
            title="Dexterous Manipulation with Diffusion Policies",
            abstract="A bimanual grasping policy improves tool use and visual servoing.",
            matched_keywords_json='[{"keyword":"manipulation"},{"keyword":"diffusion policy"}]',
        )
    ).label == "Learning / Control"
    assert classify_forest_kind(
        _paper(
            title="Robot Planning with Online Evaluation",
            abstract="We report a benchmark after deployment, but the method is a robot planner.",
            matched_keywords_json='[{"keyword":"robotics"}]',
        )
    ).label == "Evaluation / Benchmark"
    assert classify_forest_kind(
        _paper(
            title="Vision-Language Navigation with Self Awareness",
            abstract="An agent follows routes in indoor scenes.",
            matched_keywords_json='[{"keyword":"navigation"},{"keyword":"data engine","group":"World Models and Data Loop"}]',
        )
    ).label == "Navigation / Mobility"
    assert classify_forest_kind(
        _paper(
            title="Robot Data Engine for Continual Manipulation Improvement",
            abstract="A data flywheel curates real robot rollouts into a closed-loop data pipeline.",
            matched_keywords_json='[{"keyword":"data engine"}]',
        )
    ).label == "Data Loop"
    assert classify_forest_kind(
        _paper(
            title="Synthetic Robot Demonstrations from a Physics Simulator",
            abstract="The system creates synthetic data in MuJoCo for sim-to-real policy learning.",
            matched_keywords_json='[{"keyword":"synthetic data"},{"keyword":"simulator"}]',
        )
    ).label == "Simulation / Synthetic Data"
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


def test_forest_tile_uses_visual_tier_for_generated_ai_count():
    paper = _paper()
    fresh = build_forest_tile(paper, date(2026, 5, 23), 1, {}, {}, {})
    translated = build_forest_tile(
        paper,
        date(2026, 5, 23),
        1,
        {
            paper.arxiv_id: PaperAbstractTranslation(
                arxiv_id=paper.arxiv_id,
                title_content="视觉语言动作机器人策略",
                content="这是一篇关于具身机器人操作和导航的基准论文。",
                model="fake",
            )
        },
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
    two_items = build_forest_tile(
        paper,
        date(2026, 5, 23),
        1,
        {
            paper.arxiv_id: PaperAbstractTranslation(
                arxiv_id=paper.arxiv_id,
                title_content="视觉语言动作机器人策略",
                content="这是一篇关于具身机器人操作和导航的基准论文。",
                model="fake",
            )
        },
        {paper.arxiv_id: PaperSummary(arxiv_id=paper.arxiv_id, content="摘要", model="fake")},
        {},
    )
    full_package = build_forest_tile(
        paper,
        date(2026, 5, 23),
        1,
        {
            paper.arxiv_id: PaperAbstractTranslation(
                arxiv_id=paper.arxiv_id,
                title_content="视觉语言动作机器人策略",
                content="这是一篇关于具身机器人操作和导航的基准论文。",
                model="fake",
            )
        },
        {paper.arxiv_id: PaperSummary(arxiv_id=paper.arxiv_id, content="摘要", model="fake")},
        {paper.arxiv_id: PaperFullTextSummary(arxiv_id=paper.arxiv_id, content="全文", model="fake")},
    )

    assert fresh["generated_ai_count"] == 0
    assert fresh["summarized"] is False
    assert fresh["plant_stage"] == "sapling"
    assert fresh["plant_tier"] == "sapling"
    assert fresh["growth_label"] == "树苗"
    assert translated["growth"] == "translation"
    assert translated["has_translation"] is True
    assert translated["translated_title"] == "视觉语言动作机器人策略"
    assert "具身机器人操作" in translated["translated_abstract"]
    assert translated["generated_ai_count"] == 1
    assert translated["summarized"] is True
    assert translated["plant_stage"] == "tree"
    assert translated["plant_tier"] == "young"
    assert translated["growth_label"] == "幼树"
    assert [step["key"] for step in translated["growth_steps"]] == ["metadata", "grown"]
    assert summarized["summarized"] is True
    assert summarized["generated_ai_count"] == 1
    assert summarized["plant_stage"] == "tree"
    assert summarized["plant_tier"] == "young"
    assert [step["key"] for step in summarized["growth_steps"]] == ["metadata", "grown"]
    assert two_items["generated_ai_count"] == 2
    assert two_items["plant_stage"] == "tree"
    assert two_items["plant_tier"] == "mature"
    assert two_items["growth_label"] == "大树"
    assert full_package["growth"] == "full_text"
    assert full_package["summarized"] is True
    assert full_package["has_full_ai_package"] is True
    assert full_package["generated_ai_count"] == 3
    assert full_package["plant_stage"] == "tree"
    assert full_package["plant_tier"] == "ancient"
    assert full_package["growth_steps"][-1]["plant_tier"] == "ancient"


def test_forest_scene_context_is_stable_for_calendar_day():
    spring = forest_scene_context(date(2026, 5, 23))
    winter = forest_scene_context(date(2026, 12, 23))

    assert spring["season_key"] == "spring"
    assert spring["season_label"] == "春林"
    assert " · " in spring["badge"]
    assert winter["season_key"] == "winter"


def test_forest_groves_keep_taxonomy_order_instead_of_count_order():
    tiles = [
        {"filter_key": "evaluation_benchmark", "summarized": False, "high_relevance": False, "rarity": "common"},
        {"filter_key": "evaluation_benchmark", "summarized": False, "high_relevance": False, "rarity": "common"},
        {"filter_key": "evaluation_benchmark", "summarized": False, "high_relevance": False, "rarity": "common"},
        {"filter_key": "foundation", "summarized": False, "high_relevance": False, "rarity": "common"},
        {"filter_key": "ego_umi", "summarized": False, "high_relevance": False, "rarity": "common"},
        {"filter_key": "data_loop", "summarized": False, "high_relevance": False, "rarity": "common"},
    ]

    groves = forest_groves(tiles)

    assert [grove["key"] for grove in groves] == ["foundation", "ego_umi", "data_loop", "evaluation_benchmark"]


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

    client = authenticated_client(app, engine)
    payload = client.get("/api/forest?date=2026-05-23").json()
    vla_payload = client.get("/api/forest?date=2026-05-23&filter=vla").json()
    summarized_payload = client.get("/api/forest?date=2026-05-23&filter=summarized").json()
    unsummarized_payload = client.get("/api/forest?date=2026-05-23&filter=unsummarized").json()

    assert payload["date"] == "2026-05-23"
    assert payload["scene"]["season_key"] == "spring"
    assert payload["counts"]["total"] == 2
    assert payload["filters"][0]["count"] == 2
    assert payload["tiles"][0]["tree_label"] == "基座树"
    assert payload["tiles"][0]["kind"] == "foundation"
    assert payload["tiles"][0]["visual_kind"] == "vla"
    assert payload["tiles"][0]["growth_label"] == "幼树"
    assert payload["tiles"][0]["generated_ai_count"] == 1
    assert payload["tiles"][0]["plant_tier"] == "young"
    assert [step["key"] for step in payload["tiles"][0]["growth_steps"]] == ["metadata", "grown"]
    foundation_payload = client.get("/api/forest?date=2026-05-23&filter=foundation").json()
    assert len(vla_payload["tiles"]) == 1
    assert len(foundation_payload["tiles"]) == 1
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
        session.add(
            PaperAbstractTranslation(
                arxiv_id="2605.00003v1",
                title_content="机器人控制的世界模型",
                content="本文介绍用于机器人控制的世界模型方法。",
                model="fake",
            )
        )
        session.add(PaperSummary(arxiv_id="2605.00003v1", content="摘要", model="fake"))
        session.add(PaperFullTextSummary(arxiv_id="2605.00003v1", content="全文", model="fake"))
        session.commit()

    response = authenticated_client(app, engine).get("/forest?date=2026-05-23")

    assert response.status_code == 200
    assert "论文森林" in response.text
    assert "forest-shell-v2" in response.text
    assert "forest-command-v2" in response.text
    assert "forest-board-v2" in response.text
    assert "forest-sidebar-v2" in response.text
    assert "forest-map-v2" in response.text
    assert "forest-grid-v2" in response.text
    assert "forest-detail-v2" in response.text
    assert "data-forest-grove" in response.text
    assert "data-forest-tile" in response.text
    assert 'data-paper-rank="1"' in response.text
    assert 'data-plant-tier="ancient"' in response.text
    assert 'data-full-ai-package="true"' in response.text
    assert '<span class="forest-tile-rank" aria-hidden="true">#1</span>' in response.text
    assert 'data-forest-tooltip-title="World Models for Robot Control"' in response.text
    assert "forest-mote" in response.text
    assert "forest-inspector-plant" in response.text
    assert "data-forest-detail-sprite" in response.text
    assert "forest-status-pixels" in response.text
    assert "forest-growth-diary" not in response.text
    assert "forest-translation-card" in response.text
    assert "data-forest-detail-translation-card" in response.text
    assert "机器人控制的世界模型" in response.text
    assert "本文介绍用于机器人控制的世界模型方法" in response.text
    assert "forest-season-badge" in response.text
    assert "forest-growth-status-badge" in response.text
    assert "data-forest-growth-fill" in response.text
    assert "data-forest-grown-visible" in response.text
    assert "data-grove-pager" in response.text
    assert "data-grove-page-next" in response.text
    assert 'data-filter-group="topic"' in response.text
    assert 'data-filter-group="status"' in response.text
    assert "data-forest-active-topic" in response.text
    assert "data-forest-focus-clear" in response.text
    assert "forest-inspector-close" in response.text
    assert "--scatter-x" not in response.text
    assert "--scatter-y" not in response.text
    assert "forest-head" not in response.text
    assert "forest-summary" not in response.text
    assert "forest-control-dock" not in response.text
    assert 'class="forest-experience' not in response.text
    assert "forest-focus-plot" not in response.text
    assert "data-forest-focus-start" not in response.text
    assert "forest-focus-harvest-badge" not in response.text
    assert "专注苗圃" not in response.text
    assert "is-flipped" not in response.text
    assert 'data-forest-season="spring"' in response.text
    assert "春林" in response.text
    assert 'data-growth-step="grown"' not in response.text
    assert "forest-growth-icon" not in response.text
    assert "论文成长进度" not in response.text
    assert "is-full-text-plant" in response.text
    assert "is-ancient-tier" in response.text
    assert "已成长" in response.text
    assert "树苗" in response.text
    assert "Foundation Model" in response.text
    assert "VLA / Foundation" not in response.text
    assert "Ego / UMI" in response.text
    assert "Perception / Spatial" in response.text
    assert "World Model / WAM" not in response.text
    assert "Reasoning / Planning" not in response.text
    assert "Learning / Control" in response.text
    assert "Manipulation" not in response.text
    assert "Navigation / Mobility" in response.text
    assert "Data Loop" in response.text
    assert "Simulation / Synthetic Data" in response.text
    assert "Simulation / Data Loop" not in response.text
    assert "Evaluation / Benchmark" in response.text
    assert "Hardware / Teleop" in response.text
    assert "Other" in response.text
    assert "古树" in response.text


def test_forest_page_renders_large_groves_without_preview_overflow(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    app = create_app(settings=settings, engine=engine)
    with Session(engine) as session:
        for index in range(26):
            session.add(
                _paper(
                    arxiv_id=f"2605.10{index:03d}v1",
                    title=f"Dataset Benchmark Suite {index}",
                    abstract="A dataset and evaluation suite for embodied robots.",
                    matched_keywords_json='[{"keyword":"dataset"}]',
                )
            )
        session.commit()

    response = authenticated_client(app, engine).get("/forest?date=2026-05-23")

    assert response.status_code == 200
    assert response.text.count("data-forest-tile") == 26
    assert 'data-grove-overflow="true"' not in response.text
    assert 'data-grove-overflow="false"' in response.text
    assert 'data-forest-focus-grove="evaluation_benchmark"' not in response.text
    assert "forest-grove-more" not in response.text
    assert "分页查看" not in response.text


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

    response = authenticated_client(app, engine).get("/forest?date=2026-05-23")

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
    client = authenticated_client(app, engine)

    empty_response = client.get("/forest?date=2026-05-24")
    invalid_response = client.get("/forest?date=not-a-date")

    assert empty_response.status_code == 200
    assert "这一天还没有森林" in empty_response.text
    assert invalid_response.status_code == 200
    assert "无法识别" in invalid_response.text
