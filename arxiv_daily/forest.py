from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence

from .models import Paper, PaperAbstractTranslation, PaperFullTextSummary, PaperSummary
from .text import clean_latex_text, clean_translation_text, clean_translation_title, inline_text_to_html
from .taxonomy import EMBODIED_TOPICS


@dataclass(frozen=True)
class ForestKind:
    key: str
    label: str
    label_zh: str
    tree_label: str
    filter_key: str
    asset_key: str


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
    topic.key: ForestKind(topic.key, topic.label, topic.label_zh, topic.tree_label, topic.key, topic.asset_key)
    for topic in EMBODIED_TOPICS
}
FOREST_KINDS["other"] = ForestKind("other", "Other", "其他", "普通树", "other", "other")

KIND_RULES = [(topic.key, list(topic.include), list(topic.exclude)) for topic in EMBODIED_TOPICS]
KIND_RULE_MAP = {key: needles for key, needles, _excludes in KIND_RULES}
KIND_EXCLUDE_MAP = {key: excludes for key, _needles, excludes in KIND_RULES}

CLASSIFICATION_ORDER = [
    "ego_umi",
    "foundation",
    "navigation_mobility",
    "simulation_synthetic",
    "data_loop",
    "learning_control",
    "perception_spatial",
    "hardware_teleop",
    "evaluation_benchmark",
]

FILTER_ALIASES = {
    "vla": "foundation",
    "vlm": "foundation",
    "world_model": "foundation",
    "wam": "foundation",
    "dataset": "evaluation_benchmark",
    "robotics": "learning_control",
    "embodied_ai": "perception_spatial",
    "navigation": "navigation_mobility",
    "manipulation": "learning_control",
    "grasping": "learning_control",
    "simulation": "simulation_synthetic",
    "synthetic_data": "simulation_synthetic",
    "data_loop": "data_loop",
    "umi": "ego_umi",
    "ego": "ego_umi",
}

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
    "grown": {"label": "已成长", "plant_stage": "tree"},
}

PLANT_TIER_BY_GENERATED_COUNT: Dict[int, Dict[str, object]] = {
    0: {"tier": "sapling", "stage": "sapling", "label": "树苗", "rank": 0},
    1: {"tier": "young", "stage": "tree", "label": "幼树", "rank": 1},
    2: {"tier": "mature", "stage": "tree", "label": "大树", "rank": 2},
    3: {"tier": "ancient", "stage": "tree", "label": "古树", "rank": 3},
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
    "vla": 6,
    "world_model": 6,
    "dataset": 6,
    "robotics": 6,
    "embodied_ai": 6,
    "manipulation": 6,
    "navigation": 6,
    "simulation": 6,
    "hardware": 6,
    "other": 6,
}

SPRITE_CONTACT_SHIFTS = {
    "tree:dataset-0": 1.17,
    "tree:dataset-1": -1.98,
    "tree:dataset-2": -11.52,
    "tree:dataset-3": -1.08,
    "tree:dataset-4": -1.83,
    "tree:dataset-5": 11.06,
    "tree:embodied_ai-0": 1.15,
    "tree:embodied_ai-1": -5.09,
    "tree:embodied_ai-2": -12.11,
    "tree:embodied_ai-4": -5.44,
    "tree:embodied_ai-5": 11.97,
    "tree:manipulation-0": 1.56,
    "tree:manipulation-1": -3.08,
    "tree:manipulation-2": -8.79,
    "tree:manipulation-3": -1.23,
    "tree:manipulation-4": -3.83,
    "tree:manipulation-5": 8.65,
    "tree:navigation-0": -1.46,
    "tree:navigation-3": 1.44,
    "tree:other-4": -1.03,
    "tree:other-5": 1.14,
    "tree:simulation-2": -11.92,
    "tree:simulation-5": 11.66,
    "tree:vla-0": 1.05,
    "tree:vla-1": -4.49,
    "tree:vla-2": -12.00,
    "tree:vla-4": -5.43,
    "tree:vla-5": 11.54,
    "tree:world_model-0": 1.58,
    "tree:world_model-1": -12.35,
    "tree:world_model-2": -11.90,
    "tree:world_model-3": -1.15,
    "tree:world_model-4": -14.18,
    "tree:world_model-5": 11.90,
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
    for key in CLASSIFICATION_ORDER:
        needles = KIND_RULE_MAP.get(key, [])
        excludes = KIND_EXCLUDE_MAP.get(key, [])
        if excludes and any(_matches_topic(text, needle) for needle in excludes):
            continue
        if any(_matches_topic(text, needle) for needle in needles):
            return FOREST_KINDS[key]
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


def sprite_contact_shift(plant_stage: str, asset_key: str) -> float:
    return SPRITE_CONTACT_SHIFTS.get(f"{plant_stage}:{asset_key}", 0.0)


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


def generated_ai_parts(
    arxiv_id: str,
    translations_by_paper: Dict[str, PaperAbstractTranslation],
    summaries_by_paper: Dict[str, PaperSummary],
    full_text_summaries_by_paper: Dict[str, PaperFullTextSummary],
) -> List[str]:
    parts = []
    if arxiv_id in translations_by_paper:
        parts.append("摘要翻译")
    if arxiv_id in summaries_by_paper:
        parts.append("单篇总结")
    if arxiv_id in full_text_summaries_by_paper:
        parts.append("全文总结")
    return parts


def plant_tier_for_generated_count(generated_count: int) -> Dict[str, object]:
    return PLANT_TIER_BY_GENERATED_COUNT[min(max(generated_count, 0), 3)]


def forest_growth_steps(
    arxiv_id: str,
    translations_by_paper: Dict[str, PaperAbstractTranslation],
    summaries_by_paper: Dict[str, PaperSummary],
    full_text_summaries_by_paper: Dict[str, PaperFullTextSummary],
) -> List[Dict[str, object]]:
    generated_parts = generated_ai_parts(
        arxiv_id, translations_by_paper, summaries_by_paper, full_text_summaries_by_paper
    )
    tier = plant_tier_for_generated_count(len(generated_parts))
    metadata_step = GROWTH_STEP_DETAILS["metadata"]
    steps: List[Dict[str, object]] = [
        {
            "key": "metadata",
            "label": FOREST_GROWTH["metadata"].label,
            "detail": str(metadata_step["detail"]),
            "rank": 0,
            "plant_stage": str(metadata_step["plant_stage"]),
            "plant_tier": "sapling",
        }
    ]
    if generated_parts:
        steps.append(
            {
                "key": "grown",
                "label": str(tier["label"]),
                "detail": " / ".join(generated_parts),
                "rank": int(tier["rank"]),
                "plant_stage": str(tier["stage"]),
                "plant_tier": str(tier["tier"]),
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
    translation = translations_by_paper.get(paper.arxiv_id)
    translated_title = clean_translation_title(translation.title_content) if translation else ""
    translated_abstract = clean_translation_text(translation.content) if translation else ""
    matched_keywords = [str(match.get("keyword")) for match in paper.matched_keywords if match.get("keyword")]
    has_summary_record = paper.arxiv_id in summaries_by_paper
    has_full_text_record = paper.arxiv_id in full_text_summaries_by_paper
    status_parts = generated_ai_parts(
        paper.arxiv_id, translations_by_paper, summaries_by_paper, full_text_summaries_by_paper
    )
    generated_ai_count = len(status_parts)
    plant_tier_state = plant_tier_for_generated_count(generated_ai_count)
    has_ai_summary = has_summary_record or has_full_text_record
    has_full_ai_package = generated_ai_count == 3
    has_generated_ai = generated_ai_count > 0
    plant_stage = str(plant_tier_state["stage"])
    plant_tier = str(plant_tier_state["tier"])
    plant_tier_label = str(plant_tier_state["label"])
    asset = forest_asset_key(kind.asset_key, seed)
    return {
        "index": index,
        "seed": seed,
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "title_display": clean_latex_text(paper.title),
        "title_html": str(inline_text_to_html(paper.title)),
        "authors": paper.authors,
        "authors_display": ", ".join(paper.authors[:5]) + (" et al." if len(paper.authors) > 5 else ""),
        "abs_url": paper.abs_url or f"https://arxiv.org/abs/{paper.arxiv_id}",
        "abstract": paper.abstract,
        "abstract_html": str(inline_text_to_html(paper.abstract)),
        "translated_title": translated_title,
        "translated_title_html": str(inline_text_to_html(translated_title)),
        "translated_abstract": translated_abstract,
        "translated_abstract_html": str(inline_text_to_html(translated_abstract)),
        "has_translation": bool(translated_title or translated_abstract),
        "has_translation_record": paper.arxiv_id in translations_by_paper,
        "has_summary_record": has_summary_record,
        "has_full_text_record": has_full_text_record,
        "score": paper.relevance_score,
        "score_display": f"{paper.relevance_score:.1f}",
        "matched_keywords": matched_keywords,
        "matched_terms_display": ", ".join(matched_keywords),
        "primary_category": paper.primary_category,
        "categories": paper.categories,
        "categories_display": ", ".join(paper.categories),
        "kind": kind.key,
        "asset": asset,
        "visual_kind": kind.asset_key,
        "kind_label": kind.label,
        "kind_label_zh": kind.label_zh,
        "tree_label": kind.tree_label,
        "filter_key": kind.filter_key,
        "rarity": rarity.key,
        "rarity_label": rarity.label,
        "growth": growth.key,
        "growth_label": plant_tier_label,
        "growth_rank": int(plant_tier_state["rank"]),
        "growth_steps": growth_steps,
        "has_ai_summary": has_ai_summary,
        "has_full_ai_package": has_full_ai_package,
        "has_generated_ai": has_generated_ai,
        "generated_ai_count": generated_ai_count,
        "plant_stage": plant_stage,
        "plant_tier": plant_tier,
        "plant_tier_label": plant_tier_label,
        "sprite_contact_shift": sprite_contact_shift(plant_stage, asset),
        "land": LAND_VARIANTS[seed % len(LAND_VARIANTS)],
        "flip": False,
        "accent": seed % 5,
        "scatter_x": 0,
        "scatter_y": 0,
        "sway_delay": seed % 1800,
        "plant_delay": (index % 18) * 34,
        "summarized": has_generated_ai,
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
            "label_zh": kind.label_zh,
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
    return groves


def _filter_count(tiles: Optional[Sequence[Dict[str, object]]], key: str) -> Optional[int]:
    if tiles is None:
        return None
    return sum(1 for tile in tiles if filter_tile(tile, key))


def forest_topic_filters(tiles: Optional[Sequence[Dict[str, object]]] = None) -> List[Dict[str, object]]:
    items = [{"key": "all", "label": "全部主题", "label_zh": ""}]
    items.extend({"key": kind.filter_key, "label": kind.label, "label_zh": kind.label_zh} for kind in FOREST_KINDS.values())
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
    key = FILTER_ALIASES.get(filter_key or "all", filter_key or "all")
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
