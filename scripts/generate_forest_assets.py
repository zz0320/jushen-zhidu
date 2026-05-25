from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "generated"
TERRAIN_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "terrain"

TREE_CANVAS = 64
TERRAIN_CANVAS = 48
TREE_SCALE = 3
TERRAIN_SCALE = 2


KIND_ORDER = [
    "vla",
    "world_model",
    "dataset",
    "robotics",
    "embodied_ai",
    "manipulation",
    "navigation",
    "simulation",
    "other",
]

KIND_PALETTES = {
    "vla": {
        "dark": "#24522f",
        "mid": "#3f8f3f",
        "light": "#73ba56",
        "accent": "#d94b33",
        "accent2": "#ffd36b",
        "trunk": "#845535",
        "trunk_dark": "#5f3b27",
    },
    "world_model": {
        "dark": "#255a54",
        "mid": "#3d9a84",
        "light": "#77c7a3",
        "accent": "#7be7e2",
        "accent2": "#9a78f2",
        "trunk": "#6b563f",
        "trunk_dark": "#4e3b2e",
    },
    "dataset": {
        "dark": "#4f6439",
        "mid": "#75904b",
        "light": "#a4b96a",
        "accent": "#e0c982",
        "accent2": "#806844",
        "trunk": "#73573a",
        "trunk_dark": "#4f3a2a",
    },
    "robotics": {
        "dark": "#244d44",
        "mid": "#3f775d",
        "light": "#72a77d",
        "accent": "#c7d3ca",
        "accent2": "#6ed1c6",
        "trunk": "#685b48",
        "trunk_dark": "#46443a",
    },
    "embodied_ai": {
        "dark": "#6e6f2d",
        "mid": "#a6a044",
        "light": "#d8ca64",
        "accent": "#f3dd7d",
        "accent2": "#6f9a46",
        "trunk": "#7b5134",
        "trunk_dark": "#563723",
    },
    "manipulation": {
        "dark": "#2f5c38",
        "mid": "#4f8d45",
        "light": "#85bd5c",
        "accent": "#e59a41",
        "accent2": "#8f5a30",
        "trunk": "#805135",
        "trunk_dark": "#5c3925",
    },
    "navigation": {
        "dark": "#2d583d",
        "mid": "#54874d",
        "light": "#8fb65a",
        "accent": "#e4c35a",
        "accent2": "#5ba7c7",
        "trunk": "#735136",
        "trunk_dark": "#523723",
    },
    "simulation": {
        "dark": "#3b6a3c",
        "mid": "#5f9a49",
        "light": "#9fbd5d",
        "accent": "#e68655",
        "accent2": "#f1d686",
        "trunk": "#735436",
        "trunk_dark": "#523b27",
    },
    "other": {
        "dark": "#2d5c34",
        "mid": "#4d8e41",
        "light": "#79b65a",
        "accent": "#c68a43",
        "accent2": "#f0d06c",
        "trunk": "#805033",
        "trunk_dark": "#5c3823",
    },
}


def rect(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, fill: str) -> None:
    draw.rectangle((x, y, x + w - 1, y + h - 1), fill=fill)


def blob(draw: ImageDraw.ImageDraw, bbox: tuple[int, int, int, int], fill: str, outline: str) -> None:
    draw.ellipse(bbox, fill=outline)
    x1, y1, x2, y2 = bbox
    draw.ellipse((x1 + 1, y1 + 1, x2 - 1, y2 - 1), fill=fill)


def line_pixels(draw: ImageDraw.ImageDraw, points: Iterable[tuple[int, int]], fill: str) -> None:
    points_list = list(points)
    if len(points_list) > 1:
        draw.line(points_list, fill=fill, width=1)
    for x, y in points_list:
        draw.point((x, y), fill=fill)


def upscale(image: Image.Image, scale: int) -> Image.Image:
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)


def draw_trunk(draw: ImageDraw.ImageDraw, palette: dict[str, str], variant: int, slim: bool = False) -> None:
    dx = (variant - 1) // 1
    trunk = palette["trunk"]
    dark = palette["trunk_dark"]
    light = "#a87648"
    if slim:
        draw.polygon([(30 + dx, 34), (35 + dx, 35), (36 + dx, 56), (27 + dx, 56), (29 + dx, 43)], fill=dark)
        draw.polygon([(31 + dx, 36), (34 + dx, 36), (35 + dx, 55), (29 + dx, 55), (30 + dx, 43)], fill=trunk)
        rect(draw, 33 + dx, 41, 1, 12, light)
        rect(draw, 25 + dx, 55, 14, 2, dark)
        rect(draw, 22 + dx, 56, 8, 2, dark)
        rect(draw, 35 + dx, 56, 9, 2, dark)
        return

    draw.polygon([(28 + dx, 30), (37 + dx, 31), (40 + dx, 56), (24 + dx, 56), (27 + dx, 41)], fill=dark)
    draw.polygon([(30 + dx, 32), (35 + dx, 32), (38 + dx, 55), (27 + dx, 55), (29 + dx, 42)], fill=trunk)
    rect(draw, 34 + dx, 37, 2, 16, light)
    rect(draw, 27 + dx, 46, 2, 7, "#6c4329")
    rect(draw, 21 + dx, 55, 15, 3, dark)
    rect(draw, 34 + dx, 56, 13, 2, dark)
    rect(draw, 26 + dx, 52, 5, 2, "#91613d")


def draw_round_canopy(draw: ImageDraw.ImageDraw, palette: dict[str, str], variant: int) -> None:
    dark = "#1f3f2b"
    dx = variant - 1
    blobs = [
        ((23 + dx, 8, 42 + dx, 28), palette["light"]),
        ((13 + dx, 22, 35 + dx, 45), palette["mid"]),
        ((29 + dx, 20, 52 + dx, 45), palette["mid"]),
        ((19 + dx, 15, 47 + dx, 40), palette["light"]),
        ((20 + dx, 30, 44 + dx, 52), palette["dark"]),
    ]
    for bbox, color in blobs:
        blob(draw, bbox, color, dark)
    rect(draw, 22 + dx, 23, 3, 2, "#9bd472")
    rect(draw, 39 + dx, 18, 4, 2, "#9bd472")
    rect(draw, 46 + dx, 34, 2, 3, palette["dark"])


def draw_pine_canopy(draw: ImageDraw.ImageDraw, palette: dict[str, str], variant: int) -> None:
    dx = variant - 1
    outline = "#1f3f2b"
    tiers = [
        (31 + dx, 8, 16, palette["light"]),
        (31 + dx, 19, 23, palette["mid"]),
        (31 + dx, 31, 30, palette["dark"]),
    ]
    for cx, y, half, color in tiers:
        draw.polygon([(cx, y), (cx - half, y + 18), (cx + half, y + 18)], fill=outline)
        draw.polygon([(cx, y + 2), (cx - half + 3, y + 17), (cx + half - 3, y + 17)], fill=color)
    rect(draw, 26 + dx, 28, 4, 2, "#7fb98d")
    rect(draw, 36 + dx, 39, 4, 2, "#6a9f75")


def draw_cactus_tree(draw: ImageDraw.ImageDraw, palette: dict[str, str], variant: int) -> None:
    dx = variant - 1
    outline = "#2b4e2d"
    mid = palette["mid"]
    light = palette["light"]
    dark = palette["dark"]
    rect(draw, 28 + dx, 18, 12, 38, outline)
    rect(draw, 30 + dx, 19, 8, 36, mid)
    rect(draw, 31 + dx, 20, 2, 31, light)
    rect(draw, 18 + dx, 29, 10, 8, outline)
    rect(draw, 20 + dx, 28, 7, 7, mid)
    rect(draw, 18 + dx, 22, 6, 12, outline)
    rect(draw, 20 + dx, 23, 3, 10, mid)
    rect(draw, 40 + dx, 33, 11, 8, outline)
    rect(draw, 40 + dx, 34, 9, 5, mid)
    rect(draw, 47 + dx, 25, 5, 12, outline)
    rect(draw, 47 + dx, 26, 3, 10, mid)
    rect(draw, 33 + dx, 14, 6, 4, palette["accent"])
    rect(draw, 34 + dx, 13, 4, 1, palette["accent2"])
    for y in [24, 32, 40, 48]:
        rect(draw, 38 + dx, y, 1, 2, dark)
        rect(draw, 29 + dx, y + 2, 1, 2, dark)


def add_category_details(draw: ImageDraw.ImageDraw, kind: str, palette: dict[str, str], variant: int) -> None:
    dx = variant - 1
    if kind == "vla":
        for x, y in [(27, 20), (42, 24), (21, 35), (35, 38), (47, 34)]:
            rect(draw, x + dx, y, 3, 3, "#bf342c")
            rect(draw, x + dx + 1, y, 1, 1, palette["accent2"])
    elif kind == "world_model":
        for x, y in [(30, 18), (43, 30), (22, 34)]:
            draw.polygon(
                [(x + dx, y - 3), (x + dx + 3, y), (x + dx, y + 5), (x + dx - 3, y)],
                fill="#1f615f",
            )
            draw.polygon(
                [(x + dx, y - 2), (x + dx + 2, y), (x + dx, y + 3), (x + dx - 2, y)],
                fill=palette["accent"],
            )
        rect(draw, 39 + dx, 20, 2, 2, palette["accent2"])
    elif kind == "dataset":
        for x, y, w, h in [(23, 25, 6, 5), (39, 30, 7, 5), (30, 39, 6, 4)]:
            rect(draw, x + dx, y, w, h, "#5e513c")
            rect(draw, x + dx + 1, y + 1, w - 2, h - 2, palette["accent"])
            rect(draw, x + dx + 2, y + 2, w - 4, 1, palette["accent2"])
    elif kind == "robotics":
        for x, y in [(29, 25), (40, 36), (25, 41)]:
            rect(draw, x + dx, y, 4, 3, palette["accent"])
            rect(draw, x + dx + 1, y + 1, 2, 1, palette["accent2"])
        line_pixels(draw, [(33 + dx, 26), (36 + dx, 28), (39 + dx, 28)], palette["accent2"])
    elif kind == "embodied_ai":
        for x, y in [(23, 22), (31, 17), (41, 23), (27, 34), (39, 36)]:
            draw.pieslice((x + dx - 3, y - 3, x + dx + 5, y + 6), 190, 350, fill=palette["accent"])
            rect(draw, x + dx + 1, y + 2, 1, 4, palette["dark"])
    elif kind == "manipulation":
        for x, y in [(24, 30), (40, 25), (35, 40)]:
            rect(draw, x + dx, y, 5, 2, palette["accent"])
            rect(draw, x + dx + 4, y + 1, 2, 4, palette["accent2"])
            rect(draw, x + dx + 1, y - 2, 2, 2, "#f0c36d")
    elif kind == "navigation":
        rect(draw, 22 + dx, 38, 3, 14, palette["trunk_dark"])
        rect(draw, 25 + dx, 38, 11, 4, palette["accent"])
        rect(draw, 17 + dx, 33, 12, 4, palette["accent2"])
        rect(draw, 34 + dx, 44, 12, 4, palette["accent"])
        rect(draw, 44 + dx, 45, 2, 2, "#5f411f")
    elif kind == "other":
        for x, y in [(24, 33), (37, 26), (45, 37)]:
            rect(draw, x + dx, y, 3, 3, palette["accent"])
            rect(draw, x + dx + 1, y + 1, 1, 2, palette["trunk_dark"])


def draw_tree(kind: str, variant: int) -> Image.Image:
    palette = KIND_PALETTES[kind]
    image = Image.new("RGBA", (TREE_CANVAS, TREE_CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    rect(draw, 22, 57, 23, 2, "#385a34")
    rect(draw, 27, 59, 14, 1, "#8ab55e")

    if kind == "simulation":
        draw_cactus_tree(draw, palette, variant)
    else:
        draw_trunk(draw, palette, variant, slim=(kind in {"robotics", "world_model"}))
        if kind == "robotics":
            draw_pine_canopy(draw, palette, variant)
        else:
            draw_round_canopy(draw, palette, variant)
        add_category_details(draw, kind, palette, variant)

    return upscale(image, TREE_SCALE)


def draw_sapling(kind: str, variant: int) -> Image.Image:
    palette = KIND_PALETTES[kind]
    image = Image.new("RGBA", (TREE_CANVAS, TREE_CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    dx = variant - 1

    rect(draw, 27, 57, 12, 2, "#4f713c")
    if kind == "simulation":
        outline = "#2b4e2d"
        rect(draw, 30 + dx, 36, 7, 20, outline)
        rect(draw, 32 + dx, 37, 3, 18, palette["mid"])
        rect(draw, 25 + dx, 44, 7, 4, outline)
        rect(draw, 26 + dx, 43, 5, 3, palette["mid"])
        rect(draw, 25 + dx, 38, 4, 8, outline)
        rect(draw, 26 + dx, 39, 2, 6, palette["mid"])
        rect(draw, 34 + dx, 33, 4, 3, palette["accent"])
        return upscale(image, TREE_SCALE)

    rect(draw, 31 + dx, 42, 4, 14, palette["trunk_dark"])
    rect(draw, 32 + dx, 41, 2, 14, palette["trunk"])
    rect(draw, 27 + dx, 55, 11, 2, palette["trunk_dark"])

    if kind == "robotics":
        for cx, y, half, color in [
            (33 + dx, 28, 8, palette["light"]),
            (33 + dx, 36, 12, palette["mid"]),
            (33 + dx, 44, 14, palette["dark"]),
        ]:
            draw.polygon([(cx, y), (cx - half, y + 10), (cx + half, y + 10)], fill="#1f3f2b")
            draw.polygon([(cx, y + 1), (cx - half + 2, y + 9), (cx + half - 2, y + 9)], fill=color)
        rect(draw, 38 + dx, 39, 3, 2, palette["accent"])
    elif kind == "embodied_ai":
        for x, y in [(24, 35), (32, 29), (40, 36), (30, 42)]:
            draw.pieslice((x + dx - 2, y - 3, x + dx + 7, y + 6), 190, 350, fill=palette["accent"])
            rect(draw, x + dx + 1, y + 1, 1, 4, palette["dark"])
    else:
        blob(draw, (24 + dx, 32, 37 + dx, 45), palette["mid"], "#1f3f2b")
        blob(draw, (31 + dx, 28, 45 + dx, 43), palette["light"], "#1f3f2b")
        blob(draw, (27 + dx, 38, 42 + dx, 51), palette["dark"], "#1f3f2b")

    if kind == "vla":
        for x, y in [(31, 35), (40, 39)]:
            rect(draw, x + dx, y, 2, 2, palette["accent"])
    elif kind == "world_model":
        draw.polygon([(36 + dx, 34), (39 + dx, 37), (36 + dx, 41), (33 + dx, 37)], fill=palette["accent"])
    elif kind == "dataset":
        rect(draw, 35 + dx, 38, 5, 4, palette["accent"])
        rect(draw, 36 + dx, 39, 3, 1, palette["accent2"])
    elif kind == "manipulation":
        rect(draw, 36 + dx, 38, 5, 2, palette["accent"])
        rect(draw, 40 + dx, 39, 2, 3, palette["accent2"])
    elif kind == "navigation":
        rect(draw, 25 + dx, 45, 2, 8, palette["trunk_dark"])
        rect(draw, 27 + dx, 44, 9, 3, palette["accent"])
        rect(draw, 36 + dx, 45, 2, 1, palette["accent2"])
    elif kind == "other":
        rect(draw, 37 + dx, 40, 2, 2, palette["accent"])

    return upscale(image, TREE_SCALE)


def terrain_noise(draw: ImageDraw.ImageDraw, rng: random.Random, colors: list[str], count: int) -> None:
    for _ in range(count):
        x = rng.randrange(1, TERRAIN_CANVAS - 2)
        y = rng.randrange(1, TERRAIN_CANVAS - 2)
        color = rng.choice(colors)
        if rng.random() < 0.68:
            rect(draw, x, y, 1, 1, color)
        else:
            rect(draw, x, y, 2, 1, color)


def draw_terrain(kind: str) -> Image.Image:
    rng = random.Random(kind)
    bases = {
        "grass": "#76ad55",
        "moss": "#6ca34f",
        "fern": "#6fa857",
        "flower": "#7bb45a",
        "clay": "#8f9f55",
        "stone": "#718f5a",
        "water": "#6aa05c",
        "shade": "#5d8a4a",
        "sprout": "#78aa4f",
        "autumn": "#7fa253",
    }
    image = Image.new("RGBA", (TERRAIN_CANVAS, TERRAIN_CANVAS), bases[kind])
    draw = ImageDraw.Draw(image)

    terrain_noise(draw, rng, ["#5d9144", "#8fbd68", "#4e7d3e", "#9cc873"], 90)

    if kind == "moss":
        for bbox in [(5, 9, 18, 18), (28, 27, 43, 39), (15, 31, 25, 42)]:
            blob(draw, bbox, "#5d9648", "#4f8241")
    elif kind == "fern":
        for x, y in [(8, 18), (23, 11), (33, 29), (16, 35)]:
            line_pixels(draw, [(x, y), (x + 4, y + 3), (x + 8, y + 7)], "#3f7840")
            rect(draw, x + 2, y + 1, 2, 1, "#9bcd74")
            rect(draw, x + 5, y + 4, 2, 1, "#9bcd74")
    elif kind == "flower":
        for x, y, color in [(10, 31, "#e8c45d"), (34, 14, "#e27766"), (27, 35, "#f4ead0"), (16, 18, "#86c96b")]:
            rect(draw, x, y, 2, 2, color)
            rect(draw, x + 1, y + 2, 1, 1, "#416f3a")
    elif kind == "clay":
        draw.polygon([(0, 32), (12, 24), (29, 25), (48, 17), (48, 48), (0, 48)], fill="#9f7143")
        draw.polygon([(0, 37), (13, 29), (30, 31), (48, 24), (48, 48), (0, 48)], fill="#b7834e")
        for y in [34, 41]:
            line_pixels(draw, [(6, y), (18, y - 3), (31, y - 1), (42, y - 5)], "#7d5734")
    elif kind == "stone":
        for bbox in [(8, 28, 17, 35), (30, 13, 40, 21), (27, 34, 36, 40)]:
            blob(draw, bbox, "#8f9582", "#67705f")
            x1, y1, _, _ = bbox
            rect(draw, x1 + 3, y1 + 2, 2, 1, "#b4b8a4")
    elif kind == "water":
        draw.polygon([(0, 22), (12, 18), (24, 22), (34, 18), (48, 20), (48, 34), (35, 36), (22, 32), (10, 35), (0, 32)], fill="#4d9e9a")
        draw.polygon([(0, 25), (13, 22), (24, 26), (35, 22), (48, 24), (48, 29), (35, 31), (22, 28), (9, 31), (0, 29)], fill="#74c7bd")
        line_pixels(draw, [(8, 25), (17, 24), (26, 27), (37, 24)], "#d4fff0")
    elif kind == "shade":
        for bbox in [(0, 0, 28, 19), (25, 18, 48, 42), (7, 30, 25, 48)]:
            blob(draw, bbox, "#4e7c42", "#466e3b")
    elif kind == "sprout":
        for x in [7, 17, 27, 37]:
            line_pixels(draw, [(x, 12), (x + 3, 22), (x + 1, 35)], "#5b8542")
            for y in [18, 28]:
                rect(draw, x + 2, y, 2, 2, "#9fcf72")
                rect(draw, x - 1, y + 1, 2, 1, "#4f8b42")
    elif kind == "autumn":
        for x, y, color in [
            (8, 12, "#d89343"),
            (17, 33, "#c96b3d"),
            (35, 19, "#e4b85d"),
            (29, 38, "#ab5b36"),
            (41, 31, "#edc46b"),
        ]:
            rect(draw, x, y, 3, 2, color)

    return upscale(image, TERRAIN_SCALE)


def save_assets() -> int:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    TERRAIN_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for kind in KIND_ORDER:
        for variant in range(3):
            tree = draw_tree(kind, variant)
            sapling = draw_sapling(kind, variant)
            tree.save(GENERATED_DIR / f"tree-{kind}-{variant}.png")
            sapling.save(GENERATED_DIR / f"sapling-{kind}-{variant}.png")
            count += 2
        draw_tree(kind, 1).save(GENERATED_DIR / f"tree-{kind}.png")
        draw_sapling(kind, 1).save(GENERATED_DIR / f"sapling-{kind}.png")
        count += 2

    for terrain in ["grass", "moss", "fern", "flower", "clay", "stone", "water", "shade", "sprout", "autumn"]:
        draw_terrain(terrain).save(TERRAIN_DIR / f"land-{terrain}.png")
        count += 1
    return count


def build_preview(path: Path) -> None:
    cell_w = 128
    cell_h = 112
    preview = Image.new("RGBA", (cell_w * 3, cell_h * len(KIND_ORDER)), "#f4ecd2")
    for row, kind in enumerate(KIND_ORDER):
        tree = draw_tree(kind, 1).resize((96, 96), Image.Resampling.NEAREST)
        sapling = draw_sapling(kind, 1).resize((96, 96), Image.Resampling.NEAREST)
        terrain = draw_terrain(["grass", "moss", "fern", "flower", "clay", "stone", "water", "shade", "sprout"][row]).resize(
            (96, 96), Image.Resampling.NEAREST
        )
        y = row * cell_h + 8
        preview.alpha_composite(terrain, (16, y))
        preview.alpha_composite(tree, (16, y))
        preview.alpha_composite(terrain, (144, y))
        preview.alpha_composite(sapling, (144, y))
    preview.convert("RGB").save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pixel forest tree, sapling, and terrain assets.")
    parser.add_argument("--preview", type=Path, help="Optional preview montage output path.")
    args = parser.parse_args()
    count = save_assets()
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        build_preview(args.preview)
    print(f"generated {count} forest assets")


if __name__ == "__main__":
    main()
