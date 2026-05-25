from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = ROOT / "arxiv_daily" / "static" / "forest" / "reference" / "forest-sprite-reference-v2.png"
GENERATED_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "generated"
TERRAIN_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "terrain"

SPRITE_CANVAS = 288
TERRAIN_CANVAS = 64
TERRAIN_SCALE = 3
SPRITE_FRAMES = 4
SPRITE_DURATIONS = [180, 220, 180, 240]
REFERENCE_BG = (246, 235, 218)

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


def remove_reference_background(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    low = 24
    high = 58
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            distance = distance_to_bg(red, green, blue)
            if distance <= low:
                pixels[x, y] = (red, green, blue, 0)
            elif distance < high:
                next_alpha = int(alpha * ((distance - low) / (high - low)))
                pixels[x, y] = (red, green, blue, next_alpha)
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        return rgba
    return drop_tiny_alpha_components(rgba.crop(bbox))


def drop_tiny_alpha_components(image: Image.Image, min_area: int = 520) -> Image.Image:
    """Remove thin detached motion marks left by the reference sheet crop."""
    alpha = image.getchannel("A")
    alpha_pixels = alpha.load()
    width, height = image.size
    visited: set[tuple[int, int]] = set()
    remove: list[tuple[int, int]] = []

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
            if len(component) < min_area:
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
    rng = random.Random(f"terrain-v3-{kind}")
    image = Image.new("RGBA", (TERRAIN_CANVAS, TERRAIN_CANVAS), TERRAIN_BASES[kind])
    draw = ImageDraw.Draw(image)
    terrain_noise(draw, rng, ["#5d9144", "#9ac86d", "#4c7c3d", "#bedf84"], 170)

    if kind == "flower":
        for x, y, color in [(12, 41, "#f3ca55"), (45, 18, "#e26f62"), (35, 48, "#f5ead0"), (21, 23, "#90ce6b")]:
            rect(draw, x, y, 3, 3, color)
            rect(draw, x + 1, y + 3, 1, 2, "#416f3a")
    elif kind == "clay":
        draw.polygon([(0, 42), (17, 30), (39, 33), (64, 22), (64, 64), (0, 64)], fill="#9d7147")
        draw.polygon([(0, 49), (18, 37), (40, 41), (64, 31), (64, 64), (0, 64)], fill="#b68250")
    elif kind == "stone":
        for bbox in [(10, 38, 25, 49), (40, 15, 56, 28), (35, 45, 51, 56)]:
            draw.ellipse(bbox, fill="#66705e")
            inset = (bbox[0] + 2, bbox[1] + 2, bbox[2] - 2, bbox[3] - 2)
            draw.ellipse(inset, fill="#949984")
    elif kind == "water":
        draw.polygon([(0, 29), (16, 23), (32, 29), (45, 23), (64, 26), (64, 44), (46, 47), (29, 41), (13, 47), (0, 43)], fill="#4d9d98")
        draw.polygon([(0, 34), (17, 30), (32, 35), (47, 30), (64, 34), (64, 39), (46, 42), (29, 37), (12, 42), (0, 39)], fill="#77cbc1")

    return upscale(image, TERRAIN_SCALE)


def save_assets() -> int:
    if not REFERENCE_PATH.exists():
        raise FileNotFoundError(f"Missing image_gen reference sheet: {REFERENCE_PATH}")
    sheet = Image.open(REFERENCE_PATH).convert("RGBA")
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    TERRAIN_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for kind in KIND_ORDER:
        tree_base = build_reference_sprite(sheet, REFERENCE_BOXES[kind]["tree"], "tree")
        for variant in range(3):
            save_sprite(tree_base, GENERATED_DIR / f"tree-{kind}-{variant}.png", "tree")
            sapling_box = REFERENCE_BOXES[kind]["sapling"][variant]
            sapling_base = build_reference_sprite(sheet, sapling_box, "sapling")
            save_sprite(sapling_base, GENERATED_DIR / f"sapling-{kind}-{variant}.png", "sapling")
            count += 2
        save_sprite(tree_base, GENERATED_DIR / f"tree-{kind}.png", "tree")
        default_sapling = build_reference_sprite(sheet, REFERENCE_BOXES[kind]["sapling"][1], "sapling")
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
