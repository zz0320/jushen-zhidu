from arxiv_daily.daily_view import build_daily_paper_forest
from arxiv_daily.models import Paper


def test_build_daily_paper_forest_assigns_each_paper_to_one_species():
    papers = [
        Paper(
            arxiv_id="2605.10001v1",
            title="Gesture Aware Vision Language Action Policy",
            abstract="A VLA robot manipulation policy.",
            fetched_for_date="2026-05-22",
            relevance_score=22.0,
            matched_keywords_json='[{"keyword":"vla","group":"VLA and Robot Foundation Models"}]',
        ),
        Paper(
            arxiv_id="2605.10002v1",
            title="Robot Benchmark Suite",
            abstract="A dataset and benchmark for embodied evaluation.",
            fetched_for_date="2026-05-22",
            relevance_score=12.0,
            matched_keywords_json='[{"keyword":"benchmark","group":"Datasets and Benchmarks"}]',
        ),
        Paper(
            arxiv_id="2605.10003v1",
            title="Safe Deployment Constraints",
            abstract="Safe deployment and constraint handling for robot systems.",
            fetched_for_date="2026-05-22",
            relevance_score=8.0,
        ),
    ]

    forest = build_daily_paper_forest(papers)

    assert forest["total_papers"] == 3
    assert sum(grove["count"] for grove in forest["groves"]) == 3
    assert {grove["id"] for grove in forest["groves"]} == {"model-vla", "data-benchmark", "ontology-safety"}
    assert all(item["tree_height"] >= 72 for grove in forest["groves"] for item in grove["papers"])
    items = [item for grove in forest["groves"] for item in grove["papers"]]
    assert {item["tree_shape"] for item in items} == {"radiant-maple", "archive-grove", "sentinel-pine"}
    assert all(item["plot_type"] for item in items)
    assert all("tile_tilt" in item and "tile_depth" in item for item in items)
