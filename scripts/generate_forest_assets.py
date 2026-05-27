from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = ROOT / "arxiv_daily" / "static" / "forest" / "reference" / "forest-sprite-reference-v2.png"
REFERENCE_V3_PATH = ROOT / "arxiv_daily" / "static" / "forest" / "reference" / "forest-sprite-reference-v3.png"
GENERATED_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "generated"
TERRAIN_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "terrain"

SPRITE_CANVAS = 288
TERRAIN_CANVAS = 64
TERRAIN_SCALE = 3
SPRITE_FRAMES = 4
SPRITE_DURATIONS = [180, 220, 180, 240]
REFERENCE_BG = (246, 235, 218)
ASSET_VARIANTS = 6

KIND_ORDER = [
    "vla",
    "world_model",
    "dataset",
    "robotics",
    "embodied_ai",
    "manipulation",
    "navigation",
    "simulation",
    "hardware",
    "other",
]

TERRAIN_ORDER = ["grass", "moss", "fern", "flower", "clay", "stone", "water", "shade", "sprout", "autumn"]

# Boxes are measured from the image_gen reference sheet. They intentionally
# include the generated micro animation marks where present; the alpha crop
# below removes only the parchment background.
REFERENCE_BOXES = {
    "vla": {
        "tree": (15, 12, 307, 319),
        "sapling": [(355, 24, 108, 122), (355, 157, 106, 113), (15, 12, 307, 319)],
    },
    "world_model": {
        "tree": (552, 9, 265, 327),
        "sapling": [(862, 20, 92, 126), (860, 154, 98, 116), (552, 9, 265, 327)],
    },
    "dataset": {
        "tree": (1035, 13, 285, 322),
        "sapling": [(1371, 20, 108, 125), (1372, 154, 109, 115), (1035, 13, 285, 322)],
    },
    "robotics": {
        "tree": (38, 353, 258, 315),
        "sapling": [(363, 372, 97, 119), (365, 500, 93, 115), (38, 353, 258, 315)],
    },
    "embodied_ai": {
        "tree": (535, 367, 284, 300),
        "sapling": [(857, 379, 96, 112), (857, 506, 96, 108), (535, 367, 284, 300)],
    },
    "manipulation": {
        "tree": (1035, 363, 289, 304),
        "sapling": [(1374, 367, 106, 125), (1371, 503, 110, 112), (1035, 363, 289, 304)],
    },
    "navigation": {
        "tree": (25, 700, 261, 298),
        "sapling": [(363, 704, 96, 116), (363, 833, 94, 109), (25, 700, 261, 298)],
    },
    "simulation": {
        "tree": (543, 700, 265, 300),
        "sapling": [(865, 709, 88, 112), (867, 840, 86, 102), (543, 700, 265, 300)],
    },
    "other": {
        "tree": (1020, 685, 296, 315),
        "sapling": [(1376, 708, 103, 113), (1376, 831, 104, 112), (1020, 685, 296, 315)],
    },
}


def sheet_cell(col: int, row: int) -> tuple[int, int, int, int]:
    return (col * 256, row * 341, 256, 341 if row < 2 else 342)


# The v3 reference is an image_gen sheet with two fresh adult silhouettes per
# topic. These crops are deliberately cell-based so future reference sheets can
# keep the same readable 3x6 layout without recalibrating every sprite by hand.
REFERENCE_V3_BOXES = {
    "vla": [sheet_cell(0, 0), sheet_cell(1, 0)],
    "world_model": [sheet_cell(2, 0), sheet_cell(3, 0)],
    "dataset": [sheet_cell(4, 0), sheet_cell(5, 0)],
    "robotics": [sheet_cell(0, 1), sheet_cell(1, 1)],
    "embodied_ai": [sheet_cell(2, 1), sheet_cell(3, 1)],
    "manipulation": [sheet_cell(4, 1), sheet_cell(5, 1)],
    "navigation": [sheet_cell(0, 2), sheet_cell(1, 2)],
    "simulation": [sheet_cell(2, 2), sheet_cell(3, 2)],
    "hardware": [sheet_cell(4, 2), sheet_cell(5, 2)],
}

TERRAIN_BASES = {
    "grass": "#7fb65c",
    "moss": "#6ca753",
    "fern": "#70a95b",
    "flower": "#82b85d",
    "clay": "#9d7147",
    "stone": "#728f5e",
    "water": "#68a163",
    "shade": "#5c8d4f",
    "sprout": "#79ad54",
    "autumn": "#83a356",
}

TERRAIN_PALETTES = {
    "grass": ("#8fc466", "#6da64f", "#4f7d3b", "#3d5d31"),
    "moss": ("#7fba5d", "#619948", "#4b7839", "#36572c"),
    "fern": ("#8ac463", "#6aa74f", "#4d813e", "#355d30"),
    "flower": ("#96c86a", "#78ad54", "#5a8640", "#3f6332"),
    "clay": ("#b98758", "#956b43", "#704f33", "#4d3527"),
    "stone": ("#98a87d", "#788b65", "#5d704f", "#404f3c"),
    "water": ("#75b8a9", "#57988c", "#43776f", "#2f5754"),
    "shade": ("#739c62", "#557c4c", "#40613d", "#2d4630"),
    "sprout": ("#94ca64", "#72aa4f", "#56843f", "#3c6232"),
    "autumn": ("#baa45f", "#927c45", "#715e37", "#4e4029"),
}


def rect(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, fill: str) -> None:
    draw.rectangle((x, y, x + w - 1, y + h - 1), fill=fill)


def upscale(image: Image.Image, scale: int) -> Image.Image:
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)


def expanded_box(box: tuple[int, int, int, int], pad: int, sheet: Image.Image) -> tuple[int, int, int, int]:
    x, y, width, height = box
    return (
        max(0, x - pad),
        max(0, y - pad),
        min(sheet.width, x + width + pad),
        min(sheet.height, y + height + pad),
    )


def distance_to_bg(red: int, green: int, blue: int) -> float:
    return math.sqrt(
        (red - REFERENCE_BG[0]) * (red - REFERENCE_BG[0])
        + (green - REFERENCE_BG[1]) * (green - REFERENCE_BG[1])
        + (blue - REFERENCE_BG[2]) * (blue - REFERENCE_BG[2])
    )


def remove_reference_background(
    image: Image.Image,
    low: int = 24,
    high: int = 58,
    remove_edge_components: bool = False,
) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            distance = distance_to_bg(red, green, blue)
            if distance <= low:
                pixels[x, y] = (red, green, blue, 0)
            elif distance < high:
                next_alpha = int(alpha * ((distance - low) / (high - low)))
                pixels[x, y] = (red, green, blue, next_alpha)
    if remove_edge_components:
        rgba = drop_tiny_alpha_components(rgba, remove_edge_components=True)

    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        return rgba
    return drop_tiny_alpha_components(rgba.crop(bbox))


def drop_tiny_alpha_components(
    image: Image.Image,
    min_area: int = 520,
    remove_edge_components: bool = False,
    edge_margin: int = 7,
) -> Image.Image:
    """Remove thin detached motion marks left by the reference sheet crop."""
    alpha = image.getchannel("A")
    alpha_pixels = alpha.load()
    width, height = image.size
    visited: set[tuple[int, int]] = set()
    components: list[tuple[list[tuple[int, int]], int, bool]] = []

    for y in range(height):
        for x in range(width):
            if (x, y) in visited or alpha_pixels[x, y] <= 24:
                continue
            stack = [(x, y)]
            visited.add((x, y))
            component: list[tuple[int, int]] = []
            while stack:
                cx, cy = stack.pop()
                component.append((cx, cy))
                for nx in range(cx - 1, cx + 2):
                    for ny in range(cy - 1, cy + 2):
                        if nx < 0 or ny < 0 or nx >= width or ny >= height or (nx, ny) in visited:
                            continue
                        if alpha_pixels[nx, ny] > 24:
                            visited.add((nx, ny))
                            stack.append((nx, ny))
            xs = [point[0] for point in component]
            ys = [point[1] for point in component]
            touches_edge = (
                min(xs) <= edge_margin
                or max(xs) >= width - edge_margin - 1
                or min(ys) <= edge_margin
                or max(ys) >= height - edge_margin - 1
            )
            components.append((component, len(component), touches_edge))

    if not components:
        return image

    largest_area = max(area for _, area, _ in components)
    edge_area_limit = max(min_area * 4, int(largest_area * 0.38))
    remove: list[tuple[int, int]] = []
    for component, area, touches_edge in components:
        if area < min_area:
            remove.extend(component)
            continue
        if remove_edge_components and touches_edge and area < edge_area_limit:
            remove.extend(component)

    if not remove:
        return image
    cleaned = image.copy()
    cleaned_pixels = cleaned.load()
    for x, y in remove:
        red, green, blue, _ = cleaned_pixels[x, y]
        cleaned_pixels[x, y] = (red, green, blue, 0)
    bbox = cleaned.getchannel("A").getbbox()
    return cleaned.crop(bbox) if bbox else cleaned


def fit_sprite(source: Image.Image, stage: str) -> Image.Image:
    target_height = 270 if stage == "tree" else 232
    target_width = 270 if stage == "tree" else 236
    scale = min(target_width / source.width, target_height / source.height)
    width = max(1, round(source.width * scale))
    height = max(1, round(source.height * scale))
    resized = source.resize((width, height), Image.Resampling.NEAREST)
    canvas = Image.new("RGBA", (SPRITE_CANVAS, SPRITE_CANVAS), (0, 0, 0, 0))
    x = (SPRITE_CANVAS - width) // 2
    y = SPRITE_CANVAS - height - (8 if stage == "tree" else 14)
    canvas.alpha_composite(resized, (x, y))
    return canvas


def build_reference_sprite(sheet: Image.Image, box: tuple[int, int, int, int], stage: str) -> Image.Image:
    crop = sheet.crop(expanded_box(box, 12, sheet))
    transparent = remove_reference_background(crop)
    return fit_sprite(transparent, stage)


def build_v3_sprite(sheet: Image.Image, box: tuple[int, int, int, int], stage: str) -> Image.Image:
    x, y, width, height = box
    crop = sheet.crop((x, y, x + width, y + height))
    transparent = remove_reference_background(crop, low=30, high=92, remove_edge_components=True)
    return fit_sprite(transparent, stage)


def refit_sprite(source: Image.Image, stage: str) -> Image.Image:
    bbox = source.getchannel("A").getbbox()
    if bbox is None:
        return source
    return fit_sprite(source.crop(bbox), stage)


def mutate_tree_variant(base: Image.Image, variant: int, kind: str) -> Image.Image:
    if variant == 0:
        return base

    image = base
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return image

    sprite = image.crop(bbox)
    if variant in {3, 5}:
        sprite = ImageOps.mirror(sprite)

    scale_x = {1: 1.0, 2: 1.0, 3: 0.93, 4: 1.07, 5: 0.98}.get(variant, 1.0)
    scale_y = {3: 1.04, 4: 0.96, 5: 1.02}.get(variant, 1.0)
    width = max(1, round(sprite.width * scale_x))
    height = max(1, round(sprite.height * scale_y))
    sprite = sprite.resize((width, height), Image.Resampling.NEAREST)

    alpha = sprite.getchannel("A")
    rgb = sprite.convert("RGB")
    color_boost = 1.0 + (0.03 if variant in {2, 4} else -0.02 if variant == 5 else 0)
    bright_boost = 1.0 + (0.04 if variant in {1, 4} else -0.03 if variant == 3 else 0)
    rgb = ImageEnhance.Color(rgb).enhance(color_boost)
    rgb = ImageEnhance.Brightness(rgb).enhance(bright_boost)
    sprite = Image.merge("RGBA", (*rgb.split(), alpha))
    return refit_sprite(sprite, "tree")


def shift_frame(image: Image.Image, frame: int, stage: str) -> Image.Image:
    offsets = [(0, 0), (1, -1), (0, 0), (-1, -1)]
    dx, dy = offsets[frame % len(offsets)]
    if stage == "sapling":
        dx = 0 if frame in {0, 2} else dx
    canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
    frame_image = image
    if frame in {1, 2}:
        alpha = frame_image.getchannel("A")
        bright = ImageEnhance.Brightness(frame_image.convert("RGB")).enhance(1.04)
        frame_image = Image.merge("RGBA", (*bright.split(), alpha))
    canvas.alpha_composite(frame_image, (dx, dy))
    return canvas


def save_sprite(base: Image.Image, path: Path, stage: str) -> None:
    frames = [shift_frame(base, frame, stage) for frame in range(SPRITE_FRAMES)]
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


def draw_stem(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], width: int = 4) -> None:
    for dx in range(-(width // 2), width // 2 + 1):
        shifted = [(x + dx, y) for x, y in points]
        draw.line(shifted, fill="#2a3f28", width=1, joint="curve")
    draw.line(points, fill="#8a5430", width=max(1, width - 2), joint="curve")
    if width >= 4:
        draw.line([(x - 1, y) for x, y in points], fill="#c07b3e", width=1, joint="curve")


def draw_leaf(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, fill: str, outline: str = "#264729") -> None:
    draw.ellipse((x, y, x + w, y + h), fill=outline)
    draw.ellipse((x + 1, y + 1, x + w - 1, y + h - 1), fill=fill)
    rect(draw, x + w // 2, y + h // 2, 1, max(1, h // 3), "#d7f08a")


def draw_sign(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, fill: str = "#b98247") -> None:
    rect(draw, x - 1, y - 1, w + 2, h + 2, "#3a2a1d")
    rect(draw, x, y, w, h, fill)
    rect(draw, x + 2, y + h // 2, max(1, w - 4), 1, "#e1ba70")


def draw_tiny_tablet(draw: ImageDraw.ImageDraw, x: int, y: int, w: int = 10, h: int = 14) -> None:
    rect(draw, x - 1, y - 1, w + 2, h + 2, "#465047")
    rect(draw, x, y, w, h, "#bebaa0")
    rect(draw, x + 2, y + 3, w - 4, 1, "#777462")
    rect(draw, x + 2, y + 7, w - 3, 1, "#8b876f")
    rect(draw, x + 3, y + 11, w - 6, 1, "#777462")


def draw_crystal(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, fill: str = "#7ed9ff") -> None:
    outline = "#304c8e"
    draw.polygon([(x + w // 2, y - 1), (x + w, y + h // 3), (x + w - 2, y + h), (x + 2, y + h), (x, y + h // 3)], fill=outline)
    draw.polygon([(x + w // 2, y), (x + w - 1, y + h // 3), (x + w - 3, y + h - 1), (x + 3, y + h - 1), (x + 1, y + h // 3)], fill=fill)
    draw.polygon([(x + w // 2, y), (x + w - 2, y + h // 3), (x + w // 2, y + h - 1)], fill="#b9f5ff")


def draw_sapling_sprite(kind: str, variant: int) -> Image.Image:
    """Draw a young plant form that is structurally different from the adult tree."""
    rng = random.Random(f"sapling-v4-{kind}-{variant}")
    canvas = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    lean = (variant % 3) - 1
    style = variant // 3
    base_x = 48 + lean
    rect(draw, 29, 84, 38, 3, "#263b28")
    rect(draw, 34, 82, 28, 3, "#6d4a2f")

    if kind == "vla":
        draw_stem(draw, [(base_x, 82), (base_x - 1, 63), (base_x + 1, 44), (base_x + 3, 28)], 5)
        draw_leaf(draw, 27, 30 + variant, 24, 15, "#72b949")
        draw_leaf(draw, 49, 25, 25, 16, "#8bcf55")
        draw_leaf(draw, 37, 45, 22, 14, "#579b3d")
        for x, y in [(34, 37), (62, 33), (52, 49)]:
            draw.ellipse((x - 3, y - 3, x + 4, y + 4), fill="#70431e")
            draw.ellipse((x - 2, y - 2, x + 3, y + 3), fill="#ffb133")
    elif kind == "world_model":
        draw_stem(draw, [(base_x, 82), (base_x, 58), (base_x + 2, 39), (base_x + 5, 22)], 4)
        draw_crystal(draw, 24, 48, 17, 24, "#6dcaff")
        draw_crystal(draw, 43, 24, 18, 31, "#9b82ff")
        draw_crystal(draw, 58, 43, 16, 25, "#6bdfff")
        rect(draw, 35, 77, 28, 4, "#513622")
    elif kind == "dataset":
        draw_stem(draw, [(base_x, 82), (base_x - 1, 62), (base_x, 42), (base_x + 2, 28)], 5)
        draw_tiny_tablet(draw, 38, 27, 16, 24)
        draw.line((base_x, 50, 27, 43), fill="#2d442b", width=3)
        draw.line((base_x, 55, 69, 48), fill="#2d442b", width=3)
        draw_tiny_tablet(draw, 19, 36, 11, 15)
        draw_tiny_tablet(draw, 67, 42, 11, 15)
        draw_leaf(draw, 30, 58, 17, 10, "#75a94c")
    elif kind == "robotics":
        draw_stem(draw, [(base_x, 83), (base_x, 65), (base_x - 1, 48), (base_x, 28)], 5)
        for y, w in [(34, 28), (47, 40), (60, 48)]:
            draw.polygon([(base_x, y - 10), (base_x - w // 2, y + 11), (base_x + w // 2, y + 11)], fill="#263c31")
            draw.polygon([(base_x, y - 7), (base_x - w // 2 + 4, y + 8), (base_x + w // 2 - 4, y + 8)], fill="#2f6b55")
        rect(draw, base_x - 7, 48, 14, 14, "#1b2b31")
        rect(draw, base_x - 4, 51, 8, 8, "#5ad9ff")
    elif kind == "embodied_ai":
        draw_stem(draw, [(base_x, 82), (base_x - 2, 64), (base_x, 46), (base_x + 1, 30)], 4)
        for x, y, w in [(30, 32, 20), (48, 24, 23), (54, 43, 19), (37, 48, 18)]:
            draw.ellipse((x - 2, y - 2, x + w + 2, y + w + 2), fill="#5a2a3d")
            draw.ellipse((x, y, x + w, y + w), fill="#e978a7")
            draw.ellipse((x + 4, y + 3, x + w - 4, y + w - 5), fill="#ffabc9")
        for x, y in [(31, 65), (68, 61)]:
            draw.line((base_x, 51, x, y), fill="#3f2a22", width=2)
            rect(draw, x - 3, y, 7, 9, "#6b351e")
            rect(draw, x - 2, y + 1, 5, 7, "#ffb247")
    elif kind == "manipulation":
        draw_stem(draw, [(base_x, 84), (base_x + 6, 67), (base_x - 4, 49), (base_x + 4, 30)], 5)
        draw_leaf(draw, 15, 50, 20, 14, "#5d9a40")
        draw_leaf(draw, 28, 40, 22, 15, "#6fac4b")
        draw_leaf(draw, 50, 34, 25, 15, "#78bf50")
        draw.line((62, 37, 77, 30), fill="#2a3f28", width=3)
        rect(draw, 75, 24, 4, 15, "#444a42")
        draw.arc((68, 19, 86, 39), 20, 160, fill="#c5c9bb", width=3)
        draw.arc((73, 20, 91, 42), 105, 245, fill="#c5c9bb", width=3)
    elif kind == "navigation":
        draw_stem(draw, [(base_x, 84), (base_x, 62), (base_x, 42), (base_x, 21)], 5)
        draw_sign(draw, 24, 31, 24, 11)
        draw_sign(draw, 50, 45, 28, 12)
        draw_leaf(draw, 34, 55, 18, 12, "#71a84a")
        draw_leaf(draw, 54, 25, 17, 11, "#83bd50")
        rect(draw, base_x - 2, 16, 5, 7, "#e4ba60")
    elif kind == "simulation":
        draw_stem(draw, [(base_x, 84), (base_x - 1, 63), (base_x + 2, 42), (base_x + 3, 27)], 4)
        rect(draw, 32, 30, 30, 22, "#19515c")
        rect(draw, 34, 32, 26, 18, "#6be8f3")
        rect(draw, 37, 36, 8, 2, "#e8ffff")
        rect(draw, 47, 41, 8, 2, "#d0ffff")
        draw_crystal(draw, 42, 60, 15, 22, "#66e8ff")
        for x, y in [(26, 55), (66, 58), (58, 23)]:
            rect(draw, x, y, 3, 3, "#75e7ff")
        rect(draw, 68, 36, 7, 7, "#153d49")
        rect(draw, 70, 38, 3, 3, "#8ef7ff")
    elif kind == "hardware":
        draw_stem(draw, [(base_x, 84), (base_x, 64), (base_x - 2, 45), (base_x, 27)], 5)
        rect(draw, base_x - 9, 31, 18, 14, "#24393a")
        rect(draw, base_x - 6, 34, 12, 7, "#5ed4ff")
        draw.line((base_x - 4, 47, 26, 58), fill="#3c3f38", width=3)
        draw.line((base_x + 4, 48, 70, 58), fill="#3c3f38", width=3)
        for x, y in [(21, 55), (68, 55), (35, 25), (61, 24)]:
            draw.ellipse((x - 4, y - 4, x + 5, y + 5), fill="#26323b")
            draw.ellipse((x - 2, y - 2, x + 3, y + 3), fill="#b9edf5")
        if style:
            draw.line((base_x, 29, base_x - 12, 16), fill="#313b36", width=2)
            draw.line((base_x, 29, base_x + 12, 15), fill="#313b36", width=2)
            rect(draw, base_x - 14, 13, 5, 5, "#8df4ff")
            rect(draw, base_x + 10, 12, 5, 5, "#8df4ff")
    else:
        draw_stem(draw, [(base_x, 84), (base_x - 1, 65), (base_x + 1, 46), (base_x, 30)], 5)
        for x, y, w in [(27, 33, 24), (48, 28, 24), (39, 45, 26), (56, 47, 20), (30, 53, 20)]:
            draw.ellipse((x - 2, y - 2, x + w + 2, y + w + 2), fill="#203b25")
            draw.ellipse((x, y, x + w, y + w), fill=rng.choice(["#6eaf49", "#83c85b", "#5f9a3f"]))
    if style:
        draw_leaf(draw, 20 + (variant % 4) * 5, 63, 14, 9, rng.choice(["#7fc65c", "#8ed86a", "#68a84b"]))
    return upscale(canvas, 3)


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
    rng = random.Random(f"terrain-v4-plot-{kind}")
    top_color, mid_color, edge_color, outline = TERRAIN_PALETTES[kind]
    image = Image.new("RGBA", (TERRAIN_CANVAS, TERRAIN_CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    top = [(32, 7), (60, 22), (32, 39), (4, 22)]
    left_side = [(4, 22), (32, 39), (32, 49), (4, 31)]
    right_side = [(60, 22), (32, 39), (32, 49), (60, 31)]
    draw.polygon(left_side, fill=edge_color)
    draw.polygon(right_side, fill=mid_color)
    draw.polygon(top, fill=outline)
    draw.polygon([(32, 9), (57, 23), (32, 37), (7, 23)], fill=top_color)

    mask = Image.new("L", (TERRAIN_CANVAS, TERRAIN_CANVAS), 0)
    ImageDraw.Draw(mask).polygon([(32, 9), (57, 23), (32, 37), (7, 23)], fill=255)
    for _ in range(150):
        x = rng.randrange(8, 57)
        y = rng.randrange(11, 38)
        if mask.getpixel((x, y)) == 0:
            continue
        color = rng.choice([top_color, mid_color, edge_color, "#cce08a", "#5a7c3e"])
        rect(draw, x, y, 1 if rng.random() < 0.7 else 2, 1, color)

    for offset in [15, 22, 29]:
        draw.line((offset, 17, offset + 21, 29), fill=(75, 74, 42, 80), width=1)
    draw.line((8, 23, 32, 37, 56, 23), fill="#d5df86", width=1)
    draw.line((5, 31, 32, 49, 59, 31), fill=outline, width=1)

    if kind == "flower":
        for x, y, color in [(18, 24, "#f3ca55"), (44, 22, "#e26f62"), (34, 30, "#f5ead0")]:
            rect(draw, x, y, 3, 3, color)
            rect(draw, x + 1, y + 3, 1, 2, "#416f3a")
    elif kind == "clay":
        draw.line((15, 25, 38, 14), fill="#6d4930", width=1)
        draw.line((24, 32, 49, 21), fill="#6d4930", width=1)
    elif kind == "stone":
        for bbox in [(17, 24, 25, 29), (41, 18, 51, 24), (35, 29, 44, 35)]:
            draw.ellipse(bbox, fill="#66705e")
            inset = (bbox[0] + 2, bbox[1] + 2, bbox[2] - 2, bbox[3] - 2)
            draw.ellipse(inset, fill="#949984")
    elif kind == "water":
        draw.polygon([(12, 24), (23, 19), (34, 24), (45, 19), (54, 24), (45, 30), (34, 27), (23, 31)], fill="#4d9d98")
        draw.line((14, 25, 28, 22, 43, 25, 52, 23), fill="#9ff3e7", width=1)

    return upscale(image, TERRAIN_SCALE)


def save_assets() -> int:
    if not REFERENCE_PATH.exists():
        raise FileNotFoundError(f"Missing image_gen reference sheet: {REFERENCE_PATH}")
    sheet = Image.open(REFERENCE_PATH).convert("RGBA")
    v3_sheet = Image.open(REFERENCE_V3_PATH).convert("RGBA") if REFERENCE_V3_PATH.exists() else None
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    TERRAIN_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for kind in KIND_ORDER:
        if kind == "hardware":
            if v3_sheet is None:
                raise FileNotFoundError(f"Missing image_gen reference sheet: {REFERENCE_V3_PATH}")
            tree_sources = [build_v3_sprite(v3_sheet, box, "tree") for box in REFERENCE_V3_BOXES[kind]]
        else:
            tree_sources = [build_reference_sprite(sheet, REFERENCE_BOXES[kind]["tree"], "tree")]
            if v3_sheet is not None and kind in REFERENCE_V3_BOXES:
                tree_sources.extend(build_v3_sprite(v3_sheet, box, "tree") for box in REFERENCE_V3_BOXES[kind])

        for variant in range(ASSET_VARIANTS):
            source = tree_sources[min(variant, len(tree_sources) - 1) if variant < 3 else variant % len(tree_sources)]
            tree_base = mutate_tree_variant(source, variant, kind)
            save_sprite(tree_base, GENERATED_DIR / f"tree-{kind}-{variant}.png", "tree")
            sapling_base = draw_sapling_sprite(kind, variant)
            save_sprite(sapling_base, GENERATED_DIR / f"sapling-{kind}-{variant}.png", "sapling")
            count += 2
        save_sprite(tree_sources[0], GENERATED_DIR / f"tree-{kind}.png", "tree")
        default_sapling = draw_sapling_sprite(kind, 1)
        save_sprite(default_sapling, GENERATED_DIR / f"sapling-{kind}.png", "sapling")
        count += 2

    for terrain in TERRAIN_ORDER:
        draw_terrain(terrain).save(TERRAIN_DIR / f"land-{terrain}.png", optimize=True)
        count += 1
    return count


def build_preview(path: Path) -> None:
    cell_w = 160
    cell_h = 126
    preview = Image.new("RGBA", (cell_w * 3, cell_h * len(KIND_ORDER)), "#f5ecd0")
    for row, kind in enumerate(KIND_ORDER):
        tree = Image.open(GENERATED_DIR / f"tree-{kind}.png")
        tree.seek(0)
        sapling = Image.open(GENERATED_DIR / f"sapling-{kind}.png")
        sapling.seek(0)
        terrain = Image.open(TERRAIN_DIR / f"land-{TERRAIN_ORDER[row]}.png").resize((104, 104), Image.Resampling.NEAREST)
        y = row * cell_h + 10
        preview.alpha_composite(terrain, (18, y))
        preview.alpha_composite(tree.convert("RGBA").resize((104, 104), Image.Resampling.NEAREST), (18, y))
        preview.alpha_composite(terrain, (178, y))
        preview.alpha_composite(sapling.convert("RGBA").resize((104, 104), Image.Resampling.NEAREST), (178, y))
        for frame in range(SPRITE_FRAMES):
            tree.seek(frame)
            preview.alpha_composite(tree.convert("RGBA").resize((42, 42), Image.Resampling.NEAREST), (330 + frame * 28, y + 32))
    preview.convert("RGB").save(path, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract high-detail pixel forest sprites from the image_gen reference sheet.")
    parser.add_argument("--preview", type=Path, help="Optional preview montage output path.")
    args = parser.parse_args()
    count = save_assets()
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        build_preview(args.preview)
    print(f"generated {count} forest assets from {REFERENCE_PATH}")


if __name__ == "__main__":
    main()
