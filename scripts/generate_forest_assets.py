from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "generated"
TERRAIN_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "terrain"

TREE_CANVAS = 96
TERRAIN_CANVAS = 64
TREE_SCALE = 3
TERRAIN_SCALE = 3
SPRITE_FRAMES = 4
SPRITE_DURATIONS = [180, 220, 180, 240]


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

TERRAIN_ORDER = ["grass", "moss", "fern", "flower", "clay", "stone", "water", "shade", "sprout", "autumn"]

KIND_PALETTES = {
    "vla": {
        "outline": "#19351f",
        "dark": "#245b2f",
        "mid": "#3f8c3d",
        "light": "#86c45d",
        "hi": "#c8e985",
        "accent": "#f05d32",
        "accent2": "#ffd86b",
        "glow": "#fff1a6",
        "trunk": "#88552f",
        "trunk_dark": "#4f2f20",
        "trunk_light": "#c1824a",
    },
    "world_model": {
        "outline": "#173940",
        "dark": "#245d59",
        "mid": "#3b9581",
        "light": "#78cfad",
        "hi": "#c0fff0",
        "accent": "#61e6ff",
        "accent2": "#9b80ff",
        "glow": "#dffcff",
        "trunk": "#73553d",
        "trunk_dark": "#3e2d23",
        "trunk_light": "#b58155",
    },
    "dataset": {
        "outline": "#303a2c",
        "dark": "#56633c",
        "mid": "#83954f",
        "light": "#b5c66a",
        "hi": "#e1e7a2",
        "accent": "#dfcf95",
        "accent2": "#887044",
        "glow": "#fff3b8",
        "trunk": "#765238",
        "trunk_dark": "#443024",
        "trunk_light": "#ae7b4a",
    },
    "robotics": {
        "outline": "#172f31",
        "dark": "#264d46",
        "mid": "#3f765e",
        "light": "#78ab80",
        "hi": "#bdd8bd",
        "accent": "#cbd6d1",
        "accent2": "#63ddcf",
        "glow": "#d5fff8",
        "trunk": "#67604f",
        "trunk_dark": "#373832",
        "trunk_light": "#a39976",
    },
    "embodied_ai": {
        "outline": "#3d3326",
        "dark": "#895c57",
        "mid": "#c47f83",
        "light": "#eaa1ad",
        "hi": "#ffd2ce",
        "accent": "#ffc55f",
        "accent2": "#ff7f43",
        "glow": "#ffe9a2",
        "trunk": "#825335",
        "trunk_dark": "#4d301f",
        "trunk_light": "#be8050",
    },
    "manipulation": {
        "outline": "#1b3521",
        "dark": "#2d5c36",
        "mid": "#4d8e45",
        "light": "#83bd5f",
        "hi": "#c8e582",
        "accent": "#d9d3bf",
        "accent2": "#e89839",
        "glow": "#ffe2a2",
        "trunk": "#805135",
        "trunk_dark": "#4a2f22",
        "trunk_light": "#bb7b48",
    },
    "navigation": {
        "outline": "#203521",
        "dark": "#355b3b",
        "mid": "#638b4e",
        "light": "#a0bd5e",
        "hi": "#d6e782",
        "accent": "#e7bd4f",
        "accent2": "#65abc7",
        "glow": "#fff0a1",
        "trunk": "#765034",
        "trunk_dark": "#442f22",
        "trunk_light": "#ad794b",
    },
    "simulation": {
        "outline": "#173540",
        "dark": "#244e56",
        "mid": "#397f84",
        "light": "#62c9c6",
        "hi": "#c7fff6",
        "accent": "#67dcff",
        "accent2": "#8ef0d0",
        "glow": "#d6fffb",
        "trunk": "#4a4e47",
        "trunk_dark": "#282f30",
        "trunk_light": "#7a8b7e",
    },
    "other": {
        "outline": "#19351f",
        "dark": "#2d5c34",
        "mid": "#4f9042",
        "light": "#7db85d",
        "hi": "#c5de83",
        "accent": "#c98b43",
        "accent2": "#f0d06c",
        "glow": "#f5e49b",
        "trunk": "#805033",
        "trunk_dark": "#4d301f",
        "trunk_light": "#bb7b48",
    },
}


def rect(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, fill: str) -> None:
    draw.rectangle((x, y, x + w - 1, y + h - 1), fill=fill)


def blob(draw: ImageDraw.ImageDraw, bbox: tuple[int, int, int, int], fill: str, outline: str) -> None:
    draw.ellipse(bbox, fill=outline)
    x1, y1, x2, y2 = bbox
    draw.ellipse((x1 + 2, y1 + 2, x2 - 2, y2 - 2), fill=fill)


def line_pixels(draw: ImageDraw.ImageDraw, points: Iterable[tuple[int, int]], fill: str, width: int = 1) -> None:
    points_list = list(points)
    if len(points_list) > 1:
        draw.line(points_list, fill=fill, width=width)
    for x, y in points_list:
        rect(draw, x, y, width, width, fill)


def upscale(image: Image.Image, scale: int) -> Image.Image:
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)


def sway(frame: int, amount: int = 1) -> int:
    return [0, amount, 0, -amount][frame % SPRITE_FRAMES]


def pulse(frame: int) -> bool:
    return frame % SPRITE_FRAMES in {1, 2}


def variant_shift(variant: int) -> int:
    return variant - 1


def draw_ground(draw: ImageDraw.ImageDraw, palette: dict[str, str], variant: int, frame: int) -> None:
    dx = variant_shift(variant)
    shimmer = pulse(frame)
    rect(draw, 28 + dx, 84, 42, 4, "#24482d")
    rect(draw, 32 + dx, 82, 33, 3, "#517a39")
    rect(draw, 38 + dx, 80, 20, 2, palette["light"])
    rect(draw, 23 + dx, 87, 22, 2, "#5b803e")
    rect(draw, 54 + dx, 87, 18, 2, "#6a9144")
    for x, y, color in [
        (29, 81, palette["hi"]),
        (67, 83, palette["mid"]),
        (35, 88, palette["light"]),
        (59, 88, palette["hi"] if shimmer else palette["mid"]),
    ]:
        rect(draw, x + dx, y, 2, 1, color)


def draw_trunk(draw: ImageDraw.ImageDraw, palette: dict[str, str], variant: int, frame: int, slim: bool = False) -> None:
    dx = variant_shift(variant)
    lean = sway(frame)
    if slim:
        outline = [(43 + dx, 41), (53 + dx + lean, 40), (58 + dx + lean, 86), (37 + dx, 86)]
        fill = [(45 + dx, 43), (51 + dx + lean, 43), (55 + dx + lean, 84), (40 + dx, 84)]
    else:
        outline = [(39 + dx, 38), (58 + dx + lean, 39), (65 + dx + lean, 86), (31 + dx, 86)]
        fill = [(42 + dx, 41), (55 + dx + lean, 42), (61 + dx + lean, 84), (35 + dx, 84)]
    draw.polygon(outline, fill=palette["trunk_dark"])
    draw.polygon(fill, fill=palette["trunk"])
    rect(draw, 53 + dx + lean, 48, 3, 27, palette["trunk_light"])
    rect(draw, 39 + dx, 56, 3, 14, "#613a25")
    rect(draw, 27 + dx, 84, 18, 4, palette["trunk_dark"])
    rect(draw, 56 + dx + lean, 84, 20, 4, palette["trunk_dark"])
    line_pixels(draw, [(45 + dx, 48), (42 + dx, 55), (39 + dx, 61)], palette["trunk_dark"], 2)
    line_pixels(draw, [(55 + dx + lean, 51), (60 + dx + lean, 58), (63 + dx + lean, 66)], palette["trunk_light"], 1)


def draw_leaf_cluster(
    draw: ImageDraw.ImageDraw,
    palette: dict[str, str],
    cx: int,
    cy: int,
    frame: int,
    variant: int,
    wide: bool = True,
) -> None:
    dx = variant_shift(variant) + sway(frame, 2)
    top = sway(frame)
    clusters = [
        ((cx - 20 + dx, cy - 18 + top, cx + 14 + dx, cy + 12 + top), palette["light"]),
        ((cx - 36 + dx, cy - 4 + top, cx + 1 + dx, cy + 31 + top), palette["mid"]),
        ((cx + 1 + dx, cy - 2 + top, cx + 40 + dx, cy + 31 + top), palette["mid"]),
        ((cx - 20 + dx, cy + 12 + top, cx + 22 + dx, cy + 46 + top), palette["dark"]),
        ((cx - 8 + dx, cy - 31 + top, cx + 22 + dx, cy + 0 + top), palette["hi"]),
    ]
    if not wide:
        clusters = [
            ((cx - 13 + dx, cy - 23 + top, cx + 12 + dx, cy + 2 + top), palette["hi"]),
            ((cx - 26 + dx, cy - 10 + top, cx + 2 + dx, cy + 19 + top), palette["mid"]),
            ((cx + 1 + dx, cy - 9 + top, cx + 28 + dx, cy + 18 + top), palette["mid"]),
            ((cx - 16 + dx, cy + 6 + top, cx + 17 + dx, cy + 34 + top), palette["dark"]),
        ]
    for bbox, color in clusters:
        blob(draw, bbox, color, palette["outline"])
    for x, y, color in [
        (cx - 23, cy + 5, palette["hi"]),
        (cx + 16, cy - 12, palette["hi"]),
        (cx + 29, cy + 14, palette["dark"]),
        (cx - 5, cy + 24, palette["light"]),
    ]:
        rect(draw, x + dx, y + top, 4, 2, color)


def draw_pine(draw: ImageDraw.ImageDraw, palette: dict[str, str], variant: int, frame: int) -> None:
    dx = variant_shift(variant) + sway(frame, 2)
    top = sway(frame)
    tiers = [
        (48 + dx, 10 + top, 18, 20, palette["hi"]),
        (48 + dx, 24 + top, 28, 25, palette["light"]),
        (48 + dx, 41 + top, 38, 30, palette["mid"]),
        (48 + dx, 60 + top, 45, 24, palette["dark"]),
    ]
    for cx, y, half, height, color in tiers:
        draw.polygon([(cx, y), (cx - half, y + height), (cx + half, y + height)], fill=palette["outline"])
        draw.polygon([(cx, y + 3), (cx - half + 4, y + height - 1), (cx + half - 4, y + height - 1)], fill=color)
        rect(draw, cx - 5, y + height - 8, 10, 2, palette["hi"])


def draw_crystal(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, palette: dict[str, str], glow: bool) -> None:
    outline = palette["outline"]
    draw.polygon([(x, y - size), (x + size // 2, y), (x, y + size), (x - size // 2, y)], fill=outline)
    draw.polygon([(x, y - size + 2), (x + size // 2 - 2, y), (x, y + size - 2), (x - size // 2 + 2, y)], fill=palette["accent2"])
    draw.polygon([(x - 1, y - size + 4), (x + size // 2 - 3, y), (x - 1, y + size - 4)], fill=palette["accent"])
    rect(draw, x - 1, y - size + 4, 2, 5, palette["hi"] if glow else palette["light"])
    if glow:
        rect(draw, x + size // 2 + 2, y - 1, 3, 1, palette["glow"])
        rect(draw, x - size // 2 - 4, y + 1, 2, 1, palette["glow"])


def draw_tablet(draw: ImageDraw.ImageDraw, x: int, y: int, palette: dict[str, str], lit: bool = False) -> None:
    rect(draw, x - 1, y - 1, 13, 17, palette["outline"])
    rect(draw, x, y, 11, 15, palette["accent"])
    rect(draw, x + 2, y + 2, 7, 2, "#f0dfad" if lit else "#b8a06c")
    rect(draw, x + 2, y + 6, 6, 1, palette["accent2"])
    rect(draw, x + 2, y + 9, 7, 1, palette["accent2"])
    rect(draw, x + 4, y + 12, 4, 1, palette["accent2"])


def draw_circuit_box(draw: ImageDraw.ImageDraw, x: int, y: int, palette: dict[str, str], lit: bool) -> None:
    rect(draw, x - 1, y - 1, 10, 8, palette["outline"])
    rect(draw, x, y, 8, 6, palette["accent"])
    rect(draw, x + 2, y + 2, 3, 2, palette["accent2"] if lit else "#7c928e")
    line_pixels(draw, [(x + 8, y + 3), (x + 13, y + 3), (x + 13, y + 7)], palette["accent2"] if lit else palette["outline"])


def draw_lantern(draw: ImageDraw.ImageDraw, x: int, y: int, palette: dict[str, str], lit: bool) -> None:
    color = palette["glow"] if lit else palette["accent"]
    rect(draw, x, y, 8, 2, palette["trunk_dark"])
    rect(draw, x - 1, y + 2, 10, 13, palette["outline"])
    rect(draw, x + 1, y + 3, 6, 10, color)
    rect(draw, x + 2, y + 5, 4, 5, palette["accent"])
    rect(draw, x, y + 15, 8, 2, palette["trunk_dark"])


def draw_gripper(draw: ImageDraw.ImageDraw, x: int, y: int, palette: dict[str, str], lit: bool) -> None:
    metal = palette["accent"] if not lit else palette["hi"]
    rect(draw, x, y, 7, 5, palette["outline"])
    rect(draw, x + 1, y + 1, 5, 3, metal)
    line_pixels(draw, [(x + 3, y + 5), (x + 1, y + 9), (x - 2, y + 11)], palette["outline"], 2)
    line_pixels(draw, [(x + 4, y + 5), (x + 7, y + 9), (x + 10, y + 11)], palette["outline"], 2)


def draw_sign(draw: ImageDraw.ImageDraw, x: int, y: int, palette: dict[str, str], flip: bool = False) -> None:
    rect(draw, x, y, 3, 18, palette["trunk_dark"])
    if flip:
        draw.polygon([(x - 16, y + 2), (x, y + 2), (x, y + 8), (x - 16, y + 8), (x - 20, y + 5)], fill=palette["outline"])
        draw.polygon([(x - 15, y + 3), (x - 1, y + 3), (x - 1, y + 7), (x - 15, y + 7), (x - 18, y + 5)], fill=palette["accent2"])
    else:
        draw.polygon([(x, y + 2), (x + 16, y + 2), (x + 20, y + 5), (x + 16, y + 8), (x, y + 8)], fill=palette["outline"])
        draw.polygon([(x + 1, y + 3), (x + 15, y + 3), (x + 18, y + 5), (x + 15, y + 7), (x + 1, y + 7)], fill=palette["accent"])


def draw_holo_panel(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, palette: dict[str, str], lit: bool) -> None:
    rect(draw, x - 1, y - 1, w + 2, h + 2, palette["outline"])
    rect(draw, x, y, w, h, "#245c66")
    rect(draw, x + 2, y + 2, w - 4, h - 4, palette["accent"] if lit else palette["mid"])
    rect(draw, x + 5, y + 5, w - 10, 2, palette["hi"])
    rect(draw, x + 6, y + h - 6, max(2, w - 14), 1, palette["glow"] if lit else palette["accent2"])


def add_category_details(draw: ImageDraw.ImageDraw, kind: str, palette: dict[str, str], variant: int, frame: int) -> None:
    dx = variant_shift(variant) + sway(frame)
    lit = pulse(frame)
    if kind == "vla":
        for x, y, s in [(31, 25, 5), (51, 20, 6), (67, 36, 5), (27, 50, 4), (54, 55, 5), (42, 37, 4)]:
            rect(draw, x + dx, y, s, s, palette["accent"])
            rect(draw, x + dx + 1, y, max(1, s - 3), 1, palette["glow"] if lit else palette["accent2"])
    elif kind == "world_model":
        for x, y, s in [(36, 23, 11), (53, 17, 14), (66, 35, 9), (26, 45, 8), (45, 51, 10)]:
            draw_crystal(draw, x + dx, y, s, palette, lit)
        for start, end in [((43 + dx, 39), (36 + dx, 23)), ((50 + dx, 39), (53 + dx, 17)), ((56 + dx, 47), (66 + dx, 35))]:
            line_pixels(draw, [start, end], palette["trunk_dark"], 2)
    elif kind == "dataset":
        draw_tablet(draw, 24 + dx, 27, palette, lit)
        draw_tablet(draw, 56 + dx, 23, palette, lit)
        draw_tablet(draw, 40 + dx, 47, palette, False)
    elif kind == "robotics":
        draw_circuit_box(draw, 36 + dx, 28, palette, lit)
        draw_circuit_box(draw, 54 + dx, 45, palette, lit)
        rect(draw, 45 + dx, 63, 9, 6, palette["accent"])
        rect(draw, 48 + dx, 65, 3, 2, palette["accent2"] if lit else palette["outline"])
    elif kind == "embodied_ai":
        draw_lantern(draw, 25 + dx, 43, palette, lit)
        draw_lantern(draw, 63 + dx, 39, palette, lit)
        draw_lantern(draw, 45 + dx, 56, palette, False)
        line_pixels(draw, [(29 + dx, 40), (29 + dx, 43)], palette["trunk_dark"])
        line_pixels(draw, [(67 + dx, 36), (67 + dx, 39)], palette["trunk_dark"])
    elif kind == "manipulation":
        line_pixels(draw, [(25 + dx, 44), (20 + dx, 52), (21 + dx, 64)], palette["dark"], 2)
        line_pixels(draw, [(69 + dx, 37), (76 + dx, 49), (75 + dx, 61)], palette["dark"], 2)
        draw_gripper(draw, 17 + dx, 63, palette, lit)
        draw_gripper(draw, 71 + dx, 61, palette, False)
        rect(draw, 54 + dx, 31, 5, 3, palette["accent2"])
    elif kind == "navigation":
        draw_sign(draw, 31 + dx, 48, palette, False)
        draw_sign(draw, 66 + dx, 37, palette, True)
        rect(draw, 57 + dx, 28, 4, 4, palette["accent2"] if lit else palette["accent"])
    elif kind == "simulation":
        draw_holo_panel(draw, 22 + dx, 34, 18, 15, palette, lit)
        draw_holo_panel(draw, 57 + dx, 28, 20, 17, palette, lit)
        draw_holo_panel(draw, 39 + dx, 52, 22, 18, palette, False)
        rect(draw, 45 + dx, 76, 8, 6, palette["accent"] if lit else palette["mid"])
    elif kind == "other":
        for x, y in [(32, 36), (55, 30), (65, 52), (42, 57)]:
            rect(draw, x + dx, y, 4, 4, palette["accent"])
            rect(draw, x + dx + 1, y + 1, 1, 2, palette["accent2"])


def draw_tree_frame(kind: str, variant: int, frame: int) -> Image.Image:
    palette = KIND_PALETTES[kind]
    image = Image.new("RGBA", (TREE_CANVAS, TREE_CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw_ground(draw, palette, variant, frame)
    if kind == "world_model":
        draw_trunk(draw, palette, variant, frame, slim=True)
        add_category_details(draw, kind, palette, variant, frame)
    elif kind == "robotics":
        draw_trunk(draw, palette, variant, frame, slim=True)
        draw_pine(draw, palette, variant, frame)
        add_category_details(draw, kind, palette, variant, frame)
    elif kind == "simulation":
        draw_trunk(draw, palette, variant, frame, slim=True)
        draw_leaf_cluster(draw, palette, 48, 35, frame, variant, wide=False)
        add_category_details(draw, kind, palette, variant, frame)
    else:
        draw_trunk(draw, palette, variant, frame)
        draw_leaf_cluster(draw, palette, 48, 33, frame, variant, wide=True)
        add_category_details(draw, kind, palette, variant, frame)

    return upscale(image, TREE_SCALE)


def draw_sapling_frame(kind: str, variant: int, frame: int) -> Image.Image:
    palette = KIND_PALETTES[kind]
    image = Image.new("RGBA", (TREE_CANVAS, TREE_CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    dx = variant_shift(variant) + sway(frame)
    top = sway(frame)
    lit = pulse(frame)

    draw_ground(draw, palette, variant, frame)
    rect(draw, 44 + dx, 56, 10, 29, palette["trunk_dark"])
    rect(draw, 46 + dx, 55, 6, 28, palette["trunk"])
    rect(draw, 50 + dx, 61, 2, 18, palette["trunk_light"])
    rect(draw, 38 + dx, 84, 18, 3, palette["trunk_dark"])

    if kind == "world_model":
        draw_crystal(draw, 50 + dx, 45 + top, 12, palette, lit)
        draw_crystal(draw, 38 + dx, 56 + top, 7, palette, False)
        draw_crystal(draw, 61 + dx, 58 + top, 7, palette, lit)
    elif kind == "robotics":
        for cx, y, half, height, color in [
            (49 + dx, 33 + top, 11, 12, palette["hi"]),
            (49 + dx, 44 + top, 17, 16, palette["light"]),
            (49 + dx, 56 + top, 22, 18, palette["mid"]),
        ]:
            draw.polygon([(cx, y), (cx - half, y + height), (cx + half, y + height)], fill=palette["outline"])
            draw.polygon([(cx, y + 2), (cx - half + 3, y + height - 1), (cx + half - 3, y + height - 1)], fill=color)
        draw_circuit_box(draw, 54 + dx, 56, palette, lit)
    elif kind == "simulation":
        draw_leaf_cluster(draw, palette, 49, 45, frame, variant, wide=False)
        draw_holo_panel(draw, 54 + dx, 52 + top, 14, 12, palette, lit)
    else:
        draw_leaf_cluster(draw, palette, 49, 43, frame, variant, wide=False)
        if kind == "vla":
            for x, y in [(40, 45), (58, 50), (50, 57)]:
                rect(draw, x + dx, y + top, 4, 4, palette["accent"])
                rect(draw, x + dx + 1, y + top, 1, 1, palette["glow"] if lit else palette["accent2"])
        elif kind == "dataset":
            draw_tablet(draw, 55 + dx, 51 + top, palette, lit)
        elif kind == "embodied_ai":
            draw_lantern(draw, 59 + dx, 54 + top, palette, lit)
        elif kind == "manipulation":
            draw_gripper(draw, 60 + dx, 62 + top, palette, lit)
        elif kind == "navigation":
            draw_sign(draw, 40 + dx, 64 + top, palette, False)
        elif kind == "other":
            rect(draw, 57 + dx, 55 + top, 4, 4, palette["accent"])

    return upscale(image, TREE_SCALE)


def save_sprite(frames: list[Image.Image], path: Path) -> None:
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=SPRITE_DURATIONS,
        loop=0,
        disposal=2,
        blend=0,
        optimize=True,
    )


def terrain_noise(draw: ImageDraw.ImageDraw, rng: random.Random, colors: list[str], count: int) -> None:
    for _ in range(count):
        x = rng.randrange(1, TERRAIN_CANVAS - 3)
        y = rng.randrange(1, TERRAIN_CANVAS - 3)
        color = rng.choice(colors)
        if rng.random() < 0.65:
            rect(draw, x, y, 1, 1, color)
        elif rng.random() < 0.88:
            rect(draw, x, y, 2, 1, color)
        else:
            rect(draw, x, y, 2, 2, color)


def draw_terrain(kind: str) -> Image.Image:
    rng = random.Random(f"terrain-v2-{kind}")
    bases = {
        "grass": "#7fb65c",
        "moss": "#6ca753",
        "fern": "#70a95b",
        "flower": "#82b85d",
        "clay": "#8f9f55",
        "stone": "#728f5e",
        "water": "#68a163",
        "shade": "#5c8d4f",
        "sprout": "#79ad54",
        "autumn": "#83a356",
    }
    image = Image.new("RGBA", (TERRAIN_CANVAS, TERRAIN_CANVAS), bases[kind])
    draw = ImageDraw.Draw(image)

    terrain_noise(draw, rng, ["#5d9144", "#9ac86d", "#4c7c3d", "#bedf84"], 170)

    if kind == "moss":
        for bbox in [(6, 9, 26, 22), (39, 35, 61, 52), (18, 43, 34, 58)]:
            blob(draw, bbox, "#5e984c", "#4c7b40")
    elif kind == "fern":
        for x, y in [(8, 24), (27, 13), (45, 38), (18, 47)]:
            line_pixels(draw, [(x, y), (x + 6, y + 4), (x + 12, y + 10)], "#3e7740")
            rect(draw, x + 3, y + 2, 3, 1, "#afe17a")
            rect(draw, x + 8, y + 6, 3, 1, "#afe17a")
    elif kind == "flower":
        for x, y, color in [(12, 41, "#f3ca55"), (45, 18, "#e26f62"), (35, 48, "#f5ead0"), (21, 23, "#90ce6b")]:
            rect(draw, x, y, 3, 3, color)
            rect(draw, x + 1, y + 3, 1, 2, "#416f3a")
    elif kind == "clay":
        draw.polygon([(0, 42), (17, 30), (39, 33), (64, 22), (64, 64), (0, 64)], fill="#9d7147")
        draw.polygon([(0, 49), (18, 37), (40, 41), (64, 31), (64, 64), (0, 64)], fill="#b68250")
        for y in [45, 55]:
            line_pixels(draw, [(7, y), (24, y - 5), (42, y - 3), (57, y - 8)], "#765336")
    elif kind == "stone":
        for bbox in [(10, 38, 25, 49), (40, 15, 56, 28), (35, 45, 51, 56)]:
            blob(draw, bbox, "#949984", "#66705e")
            x1, y1, _, _ = bbox
            rect(draw, x1 + 4, y1 + 3, 4, 1, "#c0c4ae")
    elif kind == "water":
        draw.polygon([(0, 29), (16, 23), (32, 29), (45, 23), (64, 26), (64, 44), (46, 47), (29, 41), (13, 47), (0, 43)], fill="#4d9d98")
        draw.polygon([(0, 34), (17, 30), (32, 35), (47, 30), (64, 34), (64, 39), (46, 42), (29, 37), (12, 42), (0, 39)], fill="#77cbc1")
        line_pixels(draw, [(10, 34), (22, 32), (35, 36), (50, 32)], "#dcfff3")
    elif kind == "shade":
        for bbox in [(0, 0, 37, 24), (34, 24, 64, 54), (9, 41, 33, 64)]:
            blob(draw, bbox, "#507f45", "#436d3a")
    elif kind == "sprout":
        for x in [8, 22, 36, 50]:
            line_pixels(draw, [(x, 15), (x + 4, 31), (x + 1, 48)], "#598544")
            for y in [25, 39]:
                rect(draw, x + 3, y, 3, 3, "#a9d778")
                rect(draw, x - 1, y + 1, 3, 1, "#4f8a43")
    elif kind == "autumn":
        for x, y, color in [
            (9, 16, "#d99443"),
            (23, 44, "#c96a3d"),
            (47, 24, "#e4b95c"),
            (38, 51, "#ad5b36"),
            (55, 42, "#efc86b"),
        ]:
            rect(draw, x, y, 4, 3, color)

    return upscale(image, TERRAIN_SCALE)


def save_assets() -> int:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    TERRAIN_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for kind in KIND_ORDER:
        for variant in range(3):
            tree_frames = [draw_tree_frame(kind, variant, frame) for frame in range(SPRITE_FRAMES)]
            sapling_frames = [draw_sapling_frame(kind, variant, frame) for frame in range(SPRITE_FRAMES)]
            save_sprite(tree_frames, GENERATED_DIR / f"tree-{kind}-{variant}.png")
            save_sprite(sapling_frames, GENERATED_DIR / f"sapling-{kind}-{variant}.png")
            count += 2

        save_sprite([draw_tree_frame(kind, 1, frame) for frame in range(SPRITE_FRAMES)], GENERATED_DIR / f"tree-{kind}.png")
        save_sprite(
            [draw_sapling_frame(kind, 1, frame) for frame in range(SPRITE_FRAMES)],
            GENERATED_DIR / f"sapling-{kind}.png",
        )
        count += 2

    for terrain in TERRAIN_ORDER:
        draw_terrain(terrain).save(TERRAIN_DIR / f"land-{terrain}.png", optimize=True)
        count += 1

    return count


def build_preview(path: Path) -> None:
    cell_w = 156
    cell_h = 132
    preview = Image.new("RGBA", (cell_w * 3, cell_h * len(KIND_ORDER)), "#f5ecd0")
    terrain_names = TERRAIN_ORDER[: len(KIND_ORDER)]
    for row, kind in enumerate(KIND_ORDER):
        tree = draw_tree_frame(kind, 1, 1).resize((104, 104), Image.Resampling.NEAREST)
        sapling = draw_sapling_frame(kind, 1, 1).resize((104, 104), Image.Resampling.NEAREST)
        terrain = draw_terrain(terrain_names[row]).resize((104, 104), Image.Resampling.NEAREST)
        y = row * cell_h + 14
        preview.alpha_composite(terrain, (18, y))
        preview.alpha_composite(tree, (18, y))
        preview.alpha_composite(terrain, (174, y))
        preview.alpha_composite(sapling, (174, y))
        for frame in range(SPRITE_FRAMES):
            thumb = draw_tree_frame(kind, 1, frame).resize((42, 42), Image.Resampling.NEAREST)
            preview.alpha_composite(thumb, (326 + frame * 28, y + 30))
    preview.convert("RGB").save(path, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate high-pixel animated forest sprites and terrain assets.")
    parser.add_argument("--preview", type=Path, help="Optional preview montage output path.")
    args = parser.parse_args()
    count = save_assets()
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        build_preview(args.preview)
    print(f"generated {count} forest assets")


if __name__ == "__main__":
    main()
