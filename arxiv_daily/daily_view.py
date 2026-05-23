from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .models import Paper
from .text import clean_latex_text


DAILY_FOREST_DIMENSIONS: Sequence[Dict[str, Any]] = (
    {
        "key": "model",
        "title": "模型",
        "eyebrow": "Model Layer",
        "description": "先看方法怎么建模：VLA、world model、策略网络、空间推理和控制结构。",
        "branches": (
            {
                "key": "vla",
                "title": "VLA / 多模态策略",
                "description": "语言、视觉和动作如何接到同一个策略或机器人基础模型里。",
                "groups": {"VLA and Robot Foundation Models"},
                "terms": ("vla", "vision-language-action", "robot foundation model", "openvla", "vlm", "action model"),
                "reason": "落在模型维度的 VLA / 多模态策略分支，适合优先判断架构新意和动作生成方式。",
            },
            {
                "key": "world",
                "title": "World Model / 预测规划",
                "description": "关注状态预测、动态模型、规划器、记忆和闭环推理。",
                "groups": {"World Models and Data Loop"},
                "terms": ("world model", "dynamics", "predictive", "planning", "memory", "closed-loop"),
                "reason": "落在模型维度的 world model / 预测规划分支，适合观察是否能提升长期推理和泛化。",
            },
            {
                "key": "policy",
                "title": "Policy / 控制架构",
                "description": "策略网络、RL、Mamba/Transformer、动作专家和控制器结构。",
                "groups": {"Robotics Core", "VLA and Robot Foundation Models"},
                "terms": ("policy", "controller", "control", "reinforcement learning", "mamba", "transformer", "diffusion"),
                "reason": "落在模型维度的 policy / 控制架构分支，适合判断策略表达和控制稳定性。",
            },
            {
                "key": "spatial",
                "title": "空间推理 / 导航模型",
                "description": "3D 表征、VLN、探索、地图、空间记忆和移动规划。",
                "groups": {"Robotics Core"},
                "terms": ("navigation", "vln", "3d", "spatial", "exploration", "mapping", "map"),
                "reason": "落在模型维度的空间推理分支，适合看感知到行动之间的空间闭环。",
            },
        ),
    },
    {
        "key": "data",
        "title": "数据",
        "eyebrow": "Data Layer",
        "description": "再看数据从哪里来、怎么评测、能否形成 benchmark 或 sim-to-real 闭环。",
        "branches": (
            {
                "key": "benchmark",
                "title": "Benchmark / 评测套件",
                "description": "数据集、评测环境、leaderboard、任务套件和可复现实验平台。",
                "groups": {"Datasets and Benchmarks"},
                "terms": ("benchmark", "dataset", "evaluation", "suite", "leaderboard", "rlbench", "libero"),
                "reason": "落在数据维度的 benchmark / 评测分支，适合判断后续实验和对标价值。",
            },
            {
                "key": "sim",
                "title": "合成数据 / sim-to-real",
                "description": "仿真、合成数据、数字孪生、数据引擎和从模拟到真实迁移。",
                "groups": {"World Models and Data Loop"},
                "terms": ("synthetic data", "sim-to-real", "simulation", "simulator", "data engine", "digital twin"),
                "reason": "落在数据维度的合成数据 / sim-to-real 分支，适合跟踪可扩展训练数据来源。",
            },
            {
                "key": "human",
                "title": "人类示教 / UMI / 第一人称",
                "description": "第一人称、遥操作、可穿戴采集、示教数据和模仿学习接口。",
                "groups": {"First Person and UMI"},
                "terms": ("umi", "egocentric", "first-person", "wearable", "teleoperation", "demonstration", "imitation"),
                "reason": "落在数据维度的人类示教分支，适合看数据采集接口和行为覆盖度。",
            },
            {
                "key": "loop",
                "title": "数据闭环 / 自动构建",
                "description": "自动标注、自监督、跨传感器生成、数据飞轮和训练数据再利用。",
                "groups": {"World Models and Data Loop", "Datasets and Benchmarks"},
                "terms": ("self-supervised", "auto", "data loop", "closed-loop", "sensor2sensor", "generate data"),
                "reason": "落在数据维度的数据闭环分支，适合判断论文是否能持续扩大训练样本。",
            },
        ),
    },
    {
        "key": "ontology",
        "title": "本体",
        "eyebrow": "Embodiment Layer",
        "description": "最后看机器人身体、传感器、任务对象和真实部署约束。",
        "branches": (
            {
                "key": "body",
                "title": "机器人形态 / 硬件",
                "description": "灵巧手、夹爪、移动平台、形态差异和硬件约束。",
                "groups": {"Robot Body and Hardware"},
                "terms": ("dexterous", "hand", "gripper", "humanoid", "morphology", "hardware", "robot body"),
                "reason": "落在本体维度的机器人形态分支，适合判断方法是否依赖特定硬件。",
            },
            {
                "key": "sensor",
                "title": "传感器 / 接触",
                "description": "触觉、力控、接触、proprioception、跨传感器感知和 4D 表征。",
                "groups": {"Robot Body and Hardware"},
                "terms": ("tactile", "touch", "force", "contact", "sensor", "proprioception", "4d gaussian"),
                "reason": "落在本体维度的传感器 / 接触分支，适合看真实交互中的感知瓶颈。",
            },
            {
                "key": "task",
                "title": "任务对象 / 场景",
                "description": "操作、导航、竞速、桌面任务、家庭场景和具身任务定义。",
                "groups": {"Robotics Core"},
                "terms": ("manipulation", "navigation", "locomotion", "racing", "baoding", "scene", "object", "task"),
                "reason": "落在本体维度的任务场景分支，适合判断论文离真实应用有多近。",
            },
            {
                "key": "safety",
                "title": "安全 / 部署约束",
                "description": "安全控制、鲁棒性、失败案例、约束规划和真实部署边界。",
                "groups": {"Robotics Core"},
                "terms": ("safe", "safety", "robust", "failure", "constraint", "agile", "deployment"),
                "reason": "落在本体维度的安全 / 部署约束分支，适合判断真实系统风险和边界条件。",
            },
            {
                "key": "other",
                "title": "其他具身信号",
                "description": "没有落入前面分支，但仍命中当天扫描规则的补充论文。",
                "groups": set(),
                "terms": (),
                "fallback": True,
                "reason": "未落入核心三维分支，但仍命中当天检索规则，可作为补充浏览。",
            },
        ),
    },
)

TREE_SHAPE_BY_BRANCH = {
    "vla": "radiant-maple",
    "world": "tall-cypress",
    "policy": "wide-oak",
    "spatial": "slender-birch",
    "benchmark": "archive-grove",
    "sim": "mist-pine",
    "human": "twin-canopy",
    "loop": "spiral-sapling",
    "body": "stone-pine",
    "sensor": "glow-willow",
    "task": "harvest-oak",
    "safety": "sentinel-pine",
    "other": "quiet-shrub",
}

TREE_LABEL_BY_SHAPE = {
    "radiant-maple": "流光枫",
    "tall-cypress": "高塔柏",
    "wide-oak": "阔冠橡",
    "slender-birch": "细枝桦",
    "archive-grove": "档案树丛",
    "mist-pine": "雾松",
    "twin-canopy": "双冠树",
    "spiral-sapling": "螺旋幼树",
    "stone-pine": "石生松",
    "glow-willow": "荧光柳",
    "harvest-oak": "收获橡",
    "sentinel-pine": "哨兵松",
    "quiet-shrub": "静默灌木",
}

PLOT_TYPES_BY_BRANCH = {
    "vla": ("sunlit-moss", "flower-moss", "leaf-carpet"),
    "world": ("path-stone", "deep-moss", "sunlit-moss"),
    "policy": ("wood-root", "leaf-carpet", "deep-moss"),
    "spatial": ("path-stone", "mist-moss", "wood-root"),
    "benchmark": ("archive-stone", "path-stone", "leaf-carpet"),
    "sim": ("mist-moss", "deep-moss", "sunlit-moss"),
    "human": ("flower-moss", "leaf-carpet", "wood-root"),
    "loop": ("deep-moss", "mist-moss", "sunlit-moss"),
    "body": ("archive-stone", "wood-root", "path-stone"),
    "sensor": ("mist-moss", "flower-moss", "path-stone"),
    "task": ("leaf-carpet", "wood-root", "flower-moss"),
    "safety": ("archive-stone", "deep-moss", "path-stone"),
    "other": ("sunlit-moss", "leaf-carpet", "deep-moss"),
}

PLOT_LABEL_BY_TYPE = {
    "sunlit-moss": "日照苔地",
    "deep-moss": "深苔地",
    "leaf-carpet": "落叶地",
    "flower-moss": "花苔地",
    "path-stone": "石径地",
    "wood-root": "盘根地",
    "mist-moss": "雾苔地",
    "archive-stone": "档案石地",
}


def build_daily_keypoint_groups(papers: Sequence[Paper], max_items: int = 4) -> List[Dict[str, Any]]:
    dimensions: List[Dict[str, Any]] = []
    matched_any: set[str] = set()
    sorted_papers = sorted(papers, key=lambda paper: (paper.relevance_score, _published_ts(paper)), reverse=True)
    if not sorted_papers:
        return []
    active_branch_id = ""

    for dimension in DAILY_FOREST_DIMENSIONS:
        branches: List[Dict[str, Any]] = []
        dimension_matches: set[str] = set()

        for branch_spec in dimension["branches"]:
            if branch_spec.get("fallback"):
                branch_matches = [_paper_item(paper, branch_spec) for paper in sorted_papers if paper.arxiv_id not in matched_any]
            else:
                branch_matches = [
                    _paper_item(paper, branch_spec)
                    for paper in sorted_papers
                    if _matches_branch(paper, branch_spec)
                ]
            branch_matches = [item for item in branch_matches if item is not None]
            branch_id = f"{dimension['key']}-{branch_spec['key']}"
            if branch_matches and not active_branch_id:
                active_branch_id = branch_id
            matched_ids = {item["paper"].arxiv_id for item in branch_matches}
            matched_any.update(matched_ids)
            dimension_matches.update(matched_ids)
            branches.append(
                {
                    **branch_spec,
                    "id": branch_id,
                    "count": len(branch_matches),
                    "papers": branch_matches[:max_items],
                    "terms": _top_terms(item["paper"] for item in branch_matches),
                    "active": False,
                }
            )

        dimensions.append(
            {
                **dimension,
                "count": len(dimension_matches),
                "branches": branches,
            }
        )

    if not active_branch_id and dimensions and dimensions[0]["branches"]:
        active_branch_id = dimensions[0]["branches"][0]["id"]
    for dimension in dimensions:
        for branch in dimension["branches"]:
            branch["active"] = branch["id"] == active_branch_id

    return dimensions


def build_daily_paper_forest(papers: Sequence[Paper]) -> Dict[str, Any]:
    sorted_papers = sorted(papers, key=lambda paper: (paper.relevance_score, _published_ts(paper)), reverse=True)
    if not sorted_papers:
        return {"total_papers": 0, "species_count": 0, "plot_count": 0, "groves": [], "map": {"grid_size": 6, "papers": []}}

    branch_specs: List[Dict[str, Any]] = []
    fallback_spec: Optional[Dict[str, Any]] = None
    for dimension in DAILY_FOREST_DIMENSIONS:
        for branch in dimension["branches"]:
            spec = {
                **branch,
                "id": f"{dimension['key']}-{branch['key']}",
                "dimension_key": dimension["key"],
                "dimension_title": dimension["title"],
                "dimension_eyebrow": dimension["eyebrow"],
            }
            if branch.get("fallback"):
                fallback_spec = spec
            else:
                branch_specs.append(spec)

    grouped: Dict[str, List[Dict[str, Any]]] = {spec["id"]: [] for spec in branch_specs}
    if fallback_spec is not None:
        grouped[fallback_spec["id"]] = []

    for rank, paper in enumerate(sorted_papers, start=1):
        spec = next((branch for branch in branch_specs if _matches_branch(paper, branch)), None)
        if spec is None:
            spec = fallback_spec or branch_specs[-1]
        grouped[spec["id"]].append(_paper_tree_item(paper, spec, rank))

    groves: List[Dict[str, Any]] = []
    active_id = ""
    for spec in [*branch_specs, *([fallback_spec] if fallback_spec is not None else [])]:
        if spec is None:
            continue
        items = grouped.get(spec["id"], [])
        if not items:
            continue
        grid_size = _plot_grid_size(len(items))
        for item, (grid_row, grid_col) in zip(items, _grid_positions(len(items), grid_size)):
            item["grid_row"] = grid_row
            item["grid_col"] = grid_col
            item["grove_id"] = spec["id"]
            item["grove_key"] = spec["key"]
            item["grove_title"] = spec["title"]
            item["dimension_key"] = spec["dimension_key"]
            item["dimension_title"] = spec["dimension_title"]
        if not active_id:
            active_id = spec["id"]
        groves.append(
            {
                "id": spec["id"],
                "key": spec["key"],
                "title": spec["title"],
                "description": spec["description"],
                "dimension_key": spec["dimension_key"],
                "dimension_title": spec["dimension_title"],
                "dimension_eyebrow": spec["dimension_eyebrow"],
                "tree_shape": TREE_SHAPE_BY_BRANCH.get(spec["key"], "quiet-shrub"),
                "tree_label": TREE_LABEL_BY_SHAPE.get(TREE_SHAPE_BY_BRANCH.get(spec["key"], "quiet-shrub"), "静默灌木"),
                "count": len(items),
                "grid_cols": grid_size,
                "grid_rows": grid_size,
                "grid_label": f"{grid_size}x{grid_size}",
                "terms": _top_terms(item["paper"] for item in items),
                "papers": items,
                "active": False,
            }
        )

    for grove in groves:
        grove["active"] = grove["id"] == active_id

    map_items = sorted(
        [item for grove in groves for item in grove["papers"]],
        key=lambda item: item["rank"],
    )
    plot_count = len({item["plot_type"] for item in map_items})
    map_grid_size = _field_grid_size(len(map_items))
    map_center = (map_grid_size + 1) / 2
    for item, (grid_row, grid_col) in zip(map_items, _cluster_grid_positions(len(map_items), map_grid_size)):
        depth = 0.82 + (grid_row / max(1, map_grid_size)) * 0.24
        item["map_grid_row"] = grid_row
        item["map_grid_col"] = grid_col
        item["scene_scale"] = f"{depth:.3f}"
        item["scene_z"] = 20 + grid_row
        item["tile_z"] = 30 + grid_row * 4
        item["tree_z"] = 120 + grid_row * 4
        item["scene_shift_y"] = int((grid_row - map_center) * 1.4)

    return {
        "total_papers": len(sorted_papers),
        "species_count": len(groves),
        "plot_count": plot_count,
        "groves": groves,
        "map": {
            "grid_size": map_grid_size,
            "grid_label": f"{map_grid_size}x{map_grid_size}",
            "papers": map_items,
        },
    }


def _matches_branch(paper: Paper, spec: Dict[str, Any]) -> bool:
    paper_groups = {str(item.get("group", "")).strip() for item in paper.matched_keywords}
    if paper_groups.intersection(spec.get("groups", set())):
        return True
    haystack = _paper_haystack(paper)
    return any(_term_matches(haystack, term) for term in spec.get("terms", ()))


def _term_matches(haystack: str, term: str) -> bool:
    normalized = str(term or "").strip().lower()
    if not normalized:
        return False
    if re.fullmatch(r"[a-z0-9]+", normalized):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", haystack) is not None
    return normalized in haystack


def _paper_item(paper: Paper, spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "paper": paper,
        "reason": spec["reason"],
        "terms": _paper_terms(paper)[:4],
    }


def _paper_tree_item(paper: Paper, spec: Dict[str, Any], rank: int) -> Dict[str, Any]:
    score = max(0.0, float(paper.relevance_score or 0.0))
    tree_height = min(138, int(72 + score * 2.2))
    crown_size = min(78, max(42, int(38 + score * 1.35)))
    trunk_height = max(42, tree_height - int(crown_size * 0.38))
    pose_seed = sum(ord(char) for char in paper.arxiv_id) + rank * 17
    tree_tilt = ((pose_seed % 15) - 7) * 0.75
    tree_scale = 0.9 + ((pose_seed // 3) % 9) * 0.025
    tree_shift_x = ((pose_seed // 5) % 9) - 4
    tree_shift_y = ((pose_seed // 7) % 7) - 3
    plot_choices = PLOT_TYPES_BY_BRANCH.get(spec["key"], ("sunlit-moss",))
    plot_type = plot_choices[pose_seed % len(plot_choices)]
    tree_shape = TREE_SHAPE_BY_BRANCH.get(spec["key"], "quiet-shrub")
    tile_tilt = ((pose_seed // 11) % 7) - 3
    tile_depth = 5 + ((pose_seed // 13) % 4)
    return {
        "paper": paper,
        "rank": rank,
        "reason": spec["reason"],
        "terms": _paper_terms(paper)[:4],
        "score_label": f"{paper.relevance_score:.1f}",
        "tree_shape": tree_shape,
        "tree_label": TREE_LABEL_BY_SHAPE.get(tree_shape, "静默灌木"),
        "tree_height": tree_height,
        "crown_size": crown_size,
        "trunk_height": trunk_height,
        "tree_tilt": f"{tree_tilt:.2f}",
        "tree_scale": f"{tree_scale:.3f}",
        "tree_shift_x": tree_shift_x,
        "tree_shift_y": tree_shift_y,
        "plot_type": plot_type,
        "plot_label": PLOT_LABEL_BY_TYPE.get(plot_type, "日照苔地"),
        "tile_tilt": tile_tilt,
        "tile_depth": tile_depth,
        "delay_ms": ((rank - 1) % 16) * 42,
        "grid_row": 1,
        "grid_col": 1,
    }


def _plot_grid_size(count: int) -> int:
    if count <= 3:
        return 5
    if count <= 8:
        return 7
    return 9


def _field_grid_size(count: int) -> int:
    if count <= 81:
        return 9
    if count <= 144:
        return 12
    return min(18, int(count ** 0.5 + 0.999))


def _grid_positions(count: int, grid_size: int) -> List[tuple[int, int]]:
    if count <= 0:
        return []
    if count == 1:
        center = (grid_size + 1) // 2
        return [(center, center)]
    column_count = min(grid_size, max(1, int((count * 1.35) ** 0.5 + 0.999)))
    row_count = min(grid_size, max(1, (count + column_count - 1) // column_count))
    rows = _spread_grid_indices(row_count, grid_size)
    columns = _spread_grid_indices(column_count, grid_size)
    positions: List[tuple[int, int]] = []
    for row_index, row in enumerate(rows):
        row_columns = columns if row_index % 2 == 0 else list(reversed(columns))
        for column in row_columns:
            positions.append((row, column))
            if len(positions) == count:
                return positions
    return positions


def _cluster_grid_positions(count: int, grid_size: int) -> List[tuple[int, int]]:
    if count <= 0:
        return []
    if count == 1:
        center = (grid_size + 1) // 2
        return [(center, center)]

    center = (grid_size + 1) / 2
    candidates: List[tuple[float, int, int]] = []
    for row in range(1, grid_size + 1):
        for column in range(1, grid_size + 1):
            vertical = abs(row - center)
            horizontal = abs(column - center)
            organic_offset = ((row * 17 + column * 31) % 11) / 100
            lower_canopy_bias = (row - center) * -0.02
            score = (
                max(vertical * 1.02, horizontal * 0.9)
                + vertical * 0.18
                + horizontal * 0.08
                + organic_offset
                + lower_canopy_bias
            )
            candidates.append((score, row, column))

    selected = [(row, column) for _score, row, column in sorted(candidates)[:count]]
    return sorted(selected, key=lambda position: (position[0], position[1]))


def _spread_grid_indices(count: int, grid_size: int) -> List[int]:
    if count <= 0:
        return []
    if count >= grid_size:
        return list(range(1, grid_size + 1))
    values: List[int] = []
    used = set()
    for index in range(count):
        value = int(round((index + 1) * (grid_size + 1) / (count + 1)))
        value = min(grid_size, max(1, value))
        while value in used and value < grid_size:
            value += 1
        while value in used and value > 1:
            value -= 1
        used.add(value)
        values.append(value)
    return sorted(values)


def _paper_haystack(paper: Paper) -> str:
    return " ".join(
        [
            clean_latex_text(paper.title).lower(),
            (paper.abstract or "").lower(),
            " ".join(_paper_terms(paper)).lower(),
        ]
    )


def _paper_terms(paper: Paper) -> List[str]:
    terms: List[str] = []
    seen = set()
    for item in paper.matched_keywords:
        keyword = str(item.get("keyword", "")).strip()
        if keyword and keyword not in seen:
            seen.add(keyword)
            terms.append(keyword)
    return terms


def _top_terms(papers: Iterable[Paper], limit: int = 5) -> List[str]:
    counter: Counter[str] = Counter()
    for paper in papers:
        counter.update(_paper_terms(paper))
    return [term for term, _count in counter.most_common(limit)]


def _published_ts(paper: Paper) -> float:
    return paper.published_at.timestamp() if paper.published_at is not None else 0.0
