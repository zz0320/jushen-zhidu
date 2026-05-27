from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPRITE_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "generated"
TERRAIN_DIR = ROOT / "arxiv_daily" / "static" / "forest" / "terrain"

KINDS = [
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

TERRAINS = ["grass", "moss", "fern", "flower", "clay", "stone", "water", "shade", "sprout", "autumn"]


def _alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    image.seek(0)
    bbox = image.getchannel("A").getbbox()
    assert bbox is not None
    return bbox


def test_forest_tree_sprites_are_animated_high_pixel_assets():
    for kind in KINDS:
        for stage in ["tree", "sapling"]:
            for variant in range(6):
                path = SPRITE_DIR / f"{stage}-{kind}-{variant}.png"
                with Image.open(path) as image:
                    assert image.size == (288, 288)
                    assert getattr(image, "is_animated", False)
                    assert image.n_frames == 4

                    left, top, right, bottom = _alpha_bbox(image)
                    center_x = (left + right) / 2
                    assert abs(center_x - image.width / 2) <= 18
                    assert 0 <= left < right <= image.width
                    assert 0 <= top < bottom <= image.height
                    assert bottom <= 284
                    assert top >= 3

                    if stage == "tree":
                        min_tree_width = 120 if kind == "hardware" else 150
                        assert right - left >= min_tree_width
                        assert bottom - top >= 190
                    else:
                        assert right - left >= 135
                        assert bottom - top >= 165


def test_forest_default_sprite_aliases_and_terrain_assets_are_high_resolution():
    for kind in KINDS:
        for stage in ["tree", "sapling"]:
            path = SPRITE_DIR / f"{stage}-{kind}.png"
            with Image.open(path) as image:
                assert image.size == (288, 288)
                assert getattr(image, "is_animated", False)
                assert image.n_frames == 4

    for terrain in TERRAINS:
        path = TERRAIN_DIR / f"land-{terrain}.png"
        with Image.open(path) as image:
            assert image.size == (192, 192)
            assert image.mode == "RGBA"
