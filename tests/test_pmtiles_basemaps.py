import json
import unittest
from pathlib import Path

from milmap_engine.server import (
    DEFAULT_PROTOMAPS,
    PROTOMAPS_GLYPHS,
    PROTOMAPS_FLAVORS,
    PROTOMAPS_ORDER,
    PROTOMAPS_SPRITE_BASE,
    _florida_pmtiles_path,
)

STATIC = Path(__file__).resolve().parents[1] / "src" / "milmap_engine" / "static"
FLAVOR_DIR = STATIC / "basemaps" / "protomaps"
EXPECTED_FLAVORS = {"light", "dark", "grayscale"}


class ProtomapsFlavorTests(unittest.TestCase):
    def test_registry_shape(self):
        self.assertIn(DEFAULT_PROTOMAPS, PROTOMAPS_FLAVORS)
        self.assertEqual(set(PROTOMAPS_ORDER), set(PROTOMAPS_FLAVORS))
        self.assertEqual({cfg["flavor"] for cfg in PROTOMAPS_FLAVORS.values()}, EXPECTED_FLAVORS)
        for basemap_id, cfg in PROTOMAPS_FLAVORS.items():
            self.assertTrue(cfg["label"], basemap_id)
            self.assertTrue(cfg["purpose"], basemap_id)
            self.assertTrue(cfg["keywords"], basemap_id)

    def test_vendored_flavor_styles_exist_and_are_valid(self):
        for flavor in EXPECTED_FLAVORS:
            path = FLAVOR_DIR / f"{flavor}.json"
            self.assertTrue(path.is_file(), f"missing vendored style {path}")
            style = json.loads(path.read_text())
            self.assertIn("protomaps", style.get("sources", {}))
            self.assertTrue(style.get("layers"), f"{flavor} has no layers")

    def test_source_rewrite_targets_local_tiles(self):
        # Mirrors the rewrite performed by the /basemaps/protomaps/style route.
        style = json.loads((FLAVOR_DIR / "light.json").read_text())
        source = dict(style["sources"]["protomaps"])
        source.pop("url", None)
        source["tiles"] = ["/basemaps/florida/{z}/{x}/{y}.mvt"]
        source["maxzoom"] = 15
        self.assertEqual(source["type"], "vector")
        self.assertEqual(source["tiles"], ["/basemaps/florida/{z}/{x}/{y}.mvt"])

    def test_protomaps_asset_urls_are_local(self):
        self.assertEqual(PROTOMAPS_GLYPHS, "/static/basemaps/protomaps/fonts/{fontstack}/{range}.pbf")
        self.assertEqual(PROTOMAPS_SPRITE_BASE, "/static/basemaps/protomaps/sprites/v4")

    def test_vendored_sprites_and_glyphs_exist(self):
        for flavor in EXPECTED_FLAVORS:
            self.assertTrue((FLAVOR_DIR / "sprites" / "v4" / f"{flavor}.json").is_file(), flavor)
            self.assertTrue((FLAVOR_DIR / "sprites" / "v4" / f"{flavor}.png").is_file(), flavor)
            self.assertTrue((FLAVOR_DIR / "sprites" / "v4" / f"{flavor}@2x.json").is_file(), flavor)
            self.assertTrue((FLAVOR_DIR / "sprites" / "v4" / f"{flavor}@2x.png").is_file(), flavor)
        for font in ["Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic"]:
            self.assertTrue((FLAVOR_DIR / "fonts" / font / "0-255.pbf").is_file(), font)
            self.assertTrue((FLAVOR_DIR / "fonts" / font / "65280-65535.pbf").is_file(), font)

    def test_pmtiles_path_env_override(self):
        import os

        key = "MILMAP_PMTILES"
        prior = os.environ.get(key)
        try:
            os.environ[key] = "/tmp/custom/florida.pmtiles"
            self.assertEqual(str(_florida_pmtiles_path()), "/tmp/custom/florida.pmtiles")
        finally:
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


if __name__ == "__main__":
    unittest.main()
