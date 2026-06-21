import unittest

from milmap_engine.server import (
    BASEMAP_PURPOSE_ORDER,
    BASEMAP_REGISTRY,
    DEFAULT_BASEMAP,
)

EXPECTED_IDS = {"osm", "cartodb_dark", "opentopomap", "esri_street", "esri_topo"}
VALID_TOS = {"low", "medium", "high", "prohibited"}
REQUIRED_KEYS = {
    "label",
    "purpose",
    "tiles",
    "tile_size",
    "min_zoom",
    "max_zoom",
    "attribution",
    "keywords",
    "offline_tos",
    "offline_note",
}


class BasemapRegistryTests(unittest.TestCase):
    def test_registry_has_expected_basemaps(self):
        self.assertEqual(set(BASEMAP_REGISTRY), EXPECTED_IDS)
        self.assertIn(DEFAULT_BASEMAP, BASEMAP_REGISTRY)

    def test_purpose_order_covers_every_basemap(self):
        self.assertEqual(set(BASEMAP_PURPOSE_ORDER), EXPECTED_IDS)
        self.assertEqual(len(BASEMAP_PURPOSE_ORDER), len(set(BASEMAP_PURPOSE_ORDER)))

    def test_each_basemap_is_well_formed(self):
        for basemap_id, cfg in BASEMAP_REGISTRY.items():
            self.assertEqual(REQUIRED_KEYS, set(cfg) & REQUIRED_KEYS, f"{basemap_id} missing keys")
            self.assertTrue(cfg["tiles"], f"{basemap_id} has no tile URLs")
            self.assertTrue(cfg["attribution"], f"{basemap_id} has no attribution")
            self.assertTrue(cfg["keywords"], f"{basemap_id} has no keywords")
            self.assertIn(cfg["offline_tos"], VALID_TOS, f"{basemap_id} bad offline_tos")
            for url in cfg["tiles"]:
                self.assertIn("{z}", url)
                self.assertIn("{x}", url)
                self.assertIn("{y}", url)

    def test_tos_posture_matches_provider_policy(self):
        # Raw OSM tiles are prohibited for offline; CARTO is high-risk.
        self.assertEqual(BASEMAP_REGISTRY["osm"]["offline_tos"], "prohibited")
        self.assertEqual(BASEMAP_REGISTRY["cartodb_dark"]["offline_tos"], "high")
        self.assertEqual(BASEMAP_REGISTRY["opentopomap"]["offline_tos"], "low")


if __name__ == "__main__":
    unittest.main()
