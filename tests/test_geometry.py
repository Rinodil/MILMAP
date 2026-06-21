import unittest

from milmap_engine import SpatialAgent
from milmap_engine.geojson import GeoJSONError, normalize_geometry
from milmap_engine.geometry import buffer_point, corridor, haversine_m, hex_grid, square_grid
from milmap_engine.tools import OverpassClient, overpass_json_to_geojson


class GeometryTests(unittest.TestCase):
    def test_buffer_is_closed_and_roughly_radius_sized(self):
        center = [-82.324, 27.845]
        geom = buffer_point(center, 1000, steps=32)
        ring = geom["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(len(ring), 33)
        self.assertAlmostEqual(haversine_m(center, ring[0]), 1000, delta=2)

    def test_polygon_normalization_closes_ring(self):
        geom = normalize_geometry(
            {
                "type": "Polygon",
                "coordinates": [[[-1.123456789, 1.123456789], [0, 1], [0, 0]]],
            },
            precision=5,
        )
        ring = geom["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(ring[0], [-1.12346, 1.12346])

    def test_invalid_latitude_rejected(self):
        with self.assertRaises(GeoJSONError):
            normalize_geometry({"type": "Point", "coordinates": [10, 100]})

    def test_corridor_builds_polygon(self):
        geom = corridor([[-82.42, 27.91], [-82.35, 27.88], [-82.30, 27.83]], 750)
        self.assertEqual(geom["type"], "Polygon")
        self.assertEqual(geom["coordinates"][0][0], geom["coordinates"][0][-1])

    def test_square_grid_returns_feature_collection(self):
        collection = square_grid([-82.5, 27.7, -82.48, 27.72], 1000)
        self.assertEqual(collection["type"], "FeatureCollection")
        self.assertGreater(len(collection["features"]), 0)

    def test_hex_grid_returns_feature_collection(self):
        bounds = [-82.5, 27.7, -82.48, 27.72]
        collection = hex_grid(bounds, 500)
        self.assertEqual(collection["type"], "FeatureCollection")
        self.assertGreater(len(collection["features"]), 0)
        for item in collection["features"]:
            for ring in item["geometry"]["coordinates"]:
                for lon, lat in ring:
                    self.assertGreaterEqual(lon, bounds[0] - 0.000001)
                    self.assertLessEqual(lon, bounds[2] + 0.000001)
                    self.assertGreaterEqual(lat, bounds[1] - 0.000001)
                    self.assertLessEqual(lat, bounds[3] + 0.000001)

    def test_grid_feature_limit_is_enforced(self):
        with self.assertRaises(GeoJSONError):
            square_grid([-82.5, 27.7, -82.1, 28.0], 100, max_features=5)


class AgentTests(unittest.TestCase):
    def test_agent_executes_buffer_plan(self):
        agent = SpatialAgent()
        result = agent.execute(
            {
                "pipeline": "abstract",
                "operation": "buffer",
                "parameters": {
                    "center": [-82.324, 27.845],
                    "radius_miles": 1,
                    "steps": 16,
                },
                "properties": {"name": "test-buffer"},
            }
        )
        self.assertEqual(result["type"], "Feature")
        self.assertEqual(result["properties"]["name"], "test-buffer")
        self.assertEqual(result["geometry"]["coordinates"][0][0], result["geometry"]["coordinates"][0][-1])

    def test_agent_executes_many(self):
        agent = SpatialAgent()
        result = agent.execute_many(
            [
                {
                    "pipeline": "abstract",
                    "operation": "buffer",
                    "parameters": {"center": [-82.324, 27.845], "radius_m": 100, "steps": 8},
                },
                {
                    "pipeline": "direct",
                    "operation": "line",
                    "parameters": {"coordinates": [[-82.3, 27.8], [-82.31, 27.81]]},
                },
            ]
        )
        self.assertEqual(result["type"], "FeatureCollection")
        self.assertEqual(len(result["features"]), 2)


class ToolTests(unittest.TestCase):
    def test_overpass_boundary_query_escapes_name(self):
        client = OverpassClient(timeout_s=10)
        query = client.boundary_query('A "Quoted" Place', admin_level="8")
        self.assertIn('["name"="A \\"Quoted\\" Place"]', query)
        self.assertIn('["admin_level"="8"]', query)

    def test_overpass_json_to_geojson_converts_way(self):
        collection = overpass_json_to_geojson(
            {
                "elements": [
                    {
                        "type": "way",
                        "id": 1,
                        "tags": {"name": "Boundary"},
                        "geometry": [
                            {"lon": -1, "lat": 1},
                            {"lon": 0, "lat": 1},
                            {"lon": 0, "lat": 0},
                            {"lon": -1, "lat": 1},
                        ],
                    }
                ]
            }
        )
        self.assertEqual(collection["type"], "FeatureCollection")
        self.assertEqual(collection["features"][0]["geometry"]["type"], "Polygon")

    def test_overpass_json_to_geojson_converts_center_only_way(self):
        collection = overpass_json_to_geojson(
            {
                "elements": [
                    {
                        "type": "way",
                        "id": 2,
                        "tags": {"name": "Mall", "shop": "mall"},
                        "center": {"lon": -81.4, "lat": 28.5},
                    }
                ]
            }
        )
        self.assertEqual(collection["features"][0]["geometry"]["type"], "Point")
        self.assertEqual(collection["features"][0]["geometry"]["coordinates"], [-81.4, 28.5])


if __name__ == "__main__":
    unittest.main()
