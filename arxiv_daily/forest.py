from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence

from .models import Paper, PaperAbstractTranslation, PaperFullTextSummary, PaperSummary


@dataclass(frozen=True)
class ForestKind:
    key: str
    label: str
    tree_label: str
    filter_key: str


@dataclass(frozen=True)
class ForestRarity:
    key: str
    label: str


@dataclass(frozen=True)
class ForestGrowth:
    key: str
    label: str
    rank: int


FOREST_KINDS: Dict[str, ForestKind] = {
    "vla": ForestKind("vla", "VLA", "果树", "vla"),
    "world_model": ForestKind("world_model", "World Model", "水晶树", "world_model"),
    "dataset": ForestKind("dataset", "Dataset / Benchmark", "石碑树", "dataset"),
    "robotics": ForestKind("robotics", "Robotics", "机械松树", "robotics"),
    "embodied_ai": ForestKind("embodied_ai", "Embodied AI", "银杏树", "embodied_ai"),
    "manipulation": ForestKind("manipulation", "Manipulation", "工具树", "manipulation"),
    "navigation": ForestKind("navigation", "Navigation", "路标树", "navigation"),
    "simulation": ForestKind("simulation", "Simulation", "仙人掌树", "simulation"),
    "other": ForestKind("other", "Other", "普通树", "other"),
}

DATASET_NEEDLES = ["dataset", "benchmark", "benchmarks", "evaluation suite"]

KIND_RULES = [
    ("vla", ["vision-language-action", "vision language action", "vla"]),
    ("world_model", ["world model", "world models"]),
    ("manipulation", ["manipulation", "manipulate", "manipulator", "dexterous", "grasping"]),
    ("navigation", ["navigation", "navigate", "nav", "vln", "path planning"]),
    ("simulation", ["simulation", "sim-to-real", "simulator", "synthetic data", "digital twin"]),
    ("embodied_ai", ["embodied ai", "embodied intelligence", "embodied agent", "embodiment"]),
    ("robotics", ["robotics", "robotic", "robot", "robots"]),
    ("dataset", DATASET_NEEDLES),
]

FOREST_RARITIES: Dict[str, ForestRarity] = {
    "common": ForestRarity("common", "普通"),
    "uncommon": ForestRarity("uncommon", "少见"),
    "rare": ForestRarity("rare", "稀有"),
    "legendary": ForestRarity("legendary", "传说"),
}

FOREST_GROWTH: Dict[str, ForestGrowth] = {
    "metadata": ForestGrowth("metadata", "树苗", 0),
    "translation": ForestGrowth("translation", "幼树", 1),
    "summary": ForestGrowth("summary", "大树", 2),
    "full_text": ForestGrowth("full_text", "古树", 3),
}

GROWTH_STEP_DETAILS: Dict[str, Dict[str, object]] = {
    "metadata": {"detail": "元数据", "plant_stage": "sapling"},
    "translation": {"detail": "摘要翻译", "plant_stage": "sapling"},
    "summary": {"detail": "单篇总结", "plant_stage": "tree"},
    "full_text": {"detail": "全文总结", "plant_stage": "tree"},
}

LAND_VARIANTS = [
    "grass",
    "moss",
    "fern",
    "flower",
    "clay",
    "stone",
    "water",
    "shade",
    "sprout",
    "autumn",
]

ASSET_VARIANT_COUNTS = {
    "vla": 3,
    "world_model": 3,
    "dataset": 3,
    "robotics": 3,
    "embodied_ai": 3,
    "manipulation": 3,
    "navigation": 3,
    "simulation": 3,
    "other": 3,
}


def stable_int(*parts: object) -> int:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _paper_text(paper: Paper) -> str:
    terms = " ".join(str(match.get("keyword", "")) for match in paper.matched_keywords)
    categories = " ".join(paper.categories)
    return f"{paper.title} {paper.abstract} {terms} {paper.primary_category} {categories}".lower()


def _paper_signal_text(paper: Paper) -> str:
    terms = " ".join(str(match.get("keyword", "")) for match in paper.matched_keywords)
    categories = " ".join(paper.categories)
    return f"{paper.title} {terms} {paper.primary_category} {categories}".lower()


def classify_forest_kind(paper: Paper) -> ForestKind:
    text = _paper_text(paper)
    signal_text = _paper_signal_text(paper)
    if any(_matches_topic(signal_text, needle) for needle in DATASET_NEEDLES):
        return FOREST_KINDS["dataset"]
    for key, needles in KIND_RULES:
        if key == "dataset":
            continue
        if any(_matches_topic(text, needle) for needle in needles):
            return FOREST_KINDS[key]
    if any(_matches_topic(text, needle) for needle in DATASET_NEEDLES):
        return FOREST_KINDS["dataset"]
    return FOREST_KINDS["other"]


def _matches_topic(text: str, needle: str) -> bool:
    if len(needle) <= 4 and needle.replace("-", "").replace(" ", "").isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text) is not None
    return needle in text


def forest_asset_key(kind_key: str, seed: int) -> str:
    variant_count = ASSET_VARIANT_COUNTS.get(kind_key, 1)
    if variant_count <= 1:
        return kind_key
    return f"{kind_key}-{seed % variant_count}"


def classify_rarity(score: float) -> ForestRarity:
    if score >= 30:
        return FOREST_RARITIES["legendary"]
    if score >= 18:
        return FOREST_RARITIES["rare"]
    if score >= 8:
        return FOREST_RARITIES["uncommon"]
    return FOREST_RARITIES["common"]


def classify_growth(
    arxiv_id: str,
    translations_by_paper: Dict[str, PaperAbstractTranslation],
    summaries_by_paper: Dict[str, PaperSummary],
    full_text_summaries_by_paper: Dict[str, PaperFullTextSummary],
) -> ForestGrowth:
    if arxiv_id in full_text_summaries_by_paper:
        return FOREST_GROWTH["full_text"]
    if arxiv_id in summaries_by_paper:
        return FOREST_GROWTH["summary"]
    if arxiv_id in translations_by_paper:
        return FOREST_GROWTH["translation"]
    return FOREST_GROWTH["metadata"]


def forest_growth_steps(
    arxiv_id: str,
    translations_by_paper: Dict[str, PaperAbstractTranslation],
    summaries_by_paper: Dict[str, PaperSummary],
    full_text_summaries_by_paper: Dict[str, PaperFullTextSummary],
) -> List[Dict[str, object]]:
    keys = ["metadata"]
    if arxiv_id in translations_by_paper:
        keys.append("translation")
    if arxiv_id in summaries_by_paper:
        keys.append("summary")
    if arxiv_id in full_text_summaries_by_paper:
        keys.append("full_text")

    steps: List[Dict[str, object]] = []
    for key in keys:
        growth = FOREST_GROWTH[key]
        step = GROWTH_STEP_DETAILS[key]
        steps.append(
            {
                "key": key,
                "label": growth.label,
                "detail": str(step["detail"]),
                "rank": growth.rank,
                "plant_stage": str(step["plant_stage"]),
            }
        )
    return steps


def build_forest_tile(
    paper: Paper,
    target_day: date,
    index: int,
    translations_by_paper: Dict[str, PaperAbstractTranslation],
    summaries_by_paper: Dict[str, PaperSummary],
    full_text_summaries_by_paper: Dict[str, PaperFullTextSummary],
) -> Dict[str, object]:
    seed = stable_int(target_day.isoformat(), paper.arxiv_id)
    kind = classify_forest_kind(paper)
    rarity = classify_rarity(paper.relevance_score)
    growth = classify_growth(paper.arxiv_id, translations_by_paper, summaries_by_paper, full_text_summaries_by_paper)
    growth_steps = forest_growth_steps(
        paper.arxiv_id, translations_by_paper, summaries_by_paper, full_text_summaries_by_paper
    )
    matched_keywords = [str(match.get("keyword")) for match in paper.matched_keywords if match.get("keyword")]
    status_parts = []
    if paper.arxiv_id in translations_by_paper:
        status_parts.append("摘要翻译")
    if paper.arxiv_id in summaries_by_paper:
        status_parts.append("单篇总结")
    if paper.arxiv_id in full_text_summaries_by_paper:
        status_parts.append("全文总结")
    has_ai_summary = paper.arxiv_id in summaries_by_paper or paper.arxiv_id in full_text_summaries_by_paper
    return {
        "index": index,
        "seed": seed,
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "authors_display": ", ".join(paper.authors[:5]) + (" et al." if len(paper.authors) > 5 else ""),
        "abs_url": paper.abs_url or f"https://arxiv.org/abs/{paper.arxiv_id}",
        "abstract": paper.abstract,
        "score": paper.relevance_score,
        "score_display": f"{paper.relevance_score:.1f}",
        "matched_keywords": matched_keywords,
        "matched_terms_display": ", ".join(matched_keywords),
        "primary_category": paper.primary_category,
        "categories": paper.categories,
        "categories_display": ", ".join(paper.categories),
        "kind": kind.key,
        "asset": forest_asset_key(kind.key, seed),
        "kind_label": kind.label,
        "tree_label": kind.tree_label,
        "filter_key": kind.filter_key,
        "rarity": rarity.key,
        "rarity_label": rarity.label,
        "growth": growth.key,
        "growth_label": growth.label,
        "growth_rank": growth.rank,
        "growth_steps": growth_steps,
        "has_ai_summary": has_ai_summary,
        "plant_stage": "tree" if has_ai_summary else "sapling",
        "land": LAND_VARIANTS[seed % len(LAND_VARIANTS)],
        "flip": False,
        "accent": seed % 5,
        "scatter_x": 0,
        "scatter_y": 0,
        "sway_delay": seed % 1800,
        "plant_delay": (index % 18) * 34,
        "summarized": has_ai_summary,
        "high_relevance": rarity.key in {"rare", "legendary"},
        "summary_status": " / ".join(status_parts) if status_parts else "只有元数据",
        "detail_url": f"/papers/{paper.arxiv_id}",
    }


def build_forest_tiles(
    papers: Sequence[Paper],
    target_day: date,
    translations: Iterable[PaperAbstractTranslation],
    summaries: Iterable[PaperSummary],
    full_text_summaries: Iterable[PaperFullTextSummary],
) -> List[Dict[str, object]]:
    translations_by_paper = {translation.arxiv_id: translation for translation in translations}
    summaries_by_paper = {summary.arxiv_id: summary for summary in summaries}
    full_text_summaries_by_paper = {summary.arxiv_id: summary for summary in full_text_summaries}
    return [
        build_forest_tile(
            paper,
            target_day,
            index=index,
            translations_by_paper=translations_by_paper,
            summaries_by_paper=summaries_by_paper,
            full_text_summaries_by_paper=full_text_summaries_by_paper,
        )
        for index, paper in enumerate(papers, start=1)
    ]


def forest_client_tiles(tiles: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    hidden_fields = {"tree_label", "scatter_x", "scatter_y"}
    return [{key: value for key, value in tile.items() if key not in hidden_fields} for tile in tiles]


def forest_counts(tiles: Sequence[Dict[str, object]]) -> Dict[str, int]:
    return {
        "total": len(tiles),
        "summarized": sum(1 for tile in tiles if tile["summarized"]),
        "unsummarized": sum(1 for tile in tiles if not tile["summarized"]),
        "high_relevance": sum(1 for tile in tiles if tile["high_relevance"]),
        "legendary": sum(1 for tile in tiles if tile["rarity"] == "legendary"),
    }


def forest_scene_context(target_day: date) -> Dict[str, str]:
    if target_day.month in {3, 4, 5}:
        season_key, season_label = "spring", "春林"
    elif target_day.month in {6, 7, 8}:
        season_key, season_label = "summer", "盛夏"
    elif target_day.month in {9, 10, 11}:
        season_key, season_label = "autumn", "秋林"
    else:
        season_key, season_label = "winter", "冬林"

    moods = [
        ("clear", "晴光"),
        ("breeze", "微风"),
        ("dew", "露水"),
        ("dusk", "晚照"),
    ]
    mood_key, mood_label = moods[target_day.toordinal() % len(moods)]
    return {
        "season_key": season_key,
        "season_label": season_label,
        "mood_key": mood_key,
        "mood_label": mood_label,
        "badge": f"{season_label} · {mood_label}",
    }


def forest_groves(tiles: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, object]]] = {key: [] for key in FOREST_KINDS}
    for tile in tiles:
        key = str(tile.get("filter_key") or "other")
        if key not in grouped:
            key = "other"
        grouped[key].append(tile)

    def grove_size(count: int) -> str:
        if count >= 48:
            return "canopy"
        if count >= 18:
            return "large"
        if count >= 7:
            return "medium"
        return "small"

    groves = [
        {
            "key": kind.key,
            "label": kind.label,
            "tree_label": kind.tree_label,
            "tiles": grouped[kind.key],
            "count": len(grouped[kind.key]),
            "summarized_count": sum(1 for tile in grouped[kind.key] if tile["summarized"]),
            "sapling_count": sum(1 for tile in grouped[kind.key] if not tile["summarized"]),
            "high_relevance_count": sum(1 for tile in grouped[kind.key] if tile["high_relevance"]),
            "size": grove_size(len(grouped[kind.key])),
            "order": order,
        }
        for order, kind in enumerate(FOREST_KINDS.values())
        if grouped[kind.key]
    ]
    groves.sort(key=lambda grove: (-len(grove["tiles"]), grove["order"]))
    return groves


def _filter_count(tiles: Optional[Sequence[Dict[str, object]]], key: str) -> Optional[int]:
    if tiles is None:
        return None
    return sum(1 for tile in tiles if filter_tile(tile, key))


def forest_topic_filters(tiles: Optional[Sequence[Dict[str, object]]] = None) -> List[Dict[str, object]]:
    items = [{"key": "all", "label": "全部主题"}]
    items.extend({"key": kind.filter_key, "label": kind.label} for kind in FOREST_KINDS.values())
    return [
        {
            **item,
            "group": "topic",
            "count": len(tiles) if tiles is not None and item["key"] == "all" else _filter_count(tiles, str(item["key"])),
        }
        for item in items
    ]


def forest_status_filters(tiles: Optional[Sequence[Dict[str, object]]] = None) -> List[Dict[str, object]]:
    items = [
        {"key": "all", "label": "全部状态"},
        {"key": "summarized", "label": "已成长"},
        {"key": "unsummarized", "label": "树苗"},
        {"key": "full_text", "label": "全文古树"},
        {"key": "high_relevance", "label": "高相关"},
    ]
    return [
        {
            **item,
            "group": "status",
            "count": len(tiles) if tiles is not None and item["key"] == "all" else _filter_count(tiles, str(item["key"])),
        }
        for item in items
    ]


def forest_filters(tiles: Optional[Sequence[Dict[str, object]]] = None) -> List[Dict[str, object]]:
    return [*forest_topic_filters(tiles), *forest_status_filters(tiles)[1:]]


def filter_tile(tile: Dict[str, object], filter_key: Optional[str]) -> bool:
    key = filter_key or "all"
    if key == "all":
        return True
    if key == "summarized":
        return bool(tile["summarized"])
    if key == "unsummarized":
        return not bool(tile["summarized"])
    if key == "full_text":
        return tile["growth"] == "full_text"
    if key == "high_relevance":
        return bool(tile["high_relevance"])
    return tile["filter_key"] == key
